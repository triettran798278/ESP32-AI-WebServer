"""
Persistent Device & Provisioning Database for Platform Bridge.
Handles cryptographic token hashing, activation codes, rate-limiting,
and authenticated hardware lifecycle tracking via SQLite.
"""

import hashlib
import logging
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("platform_bridge.device_db")

DB_DIR = Path(os.getenv("PLATFORM_DATA_DIR", "/app/data" if os.path.exists("/app") else "./data"))
DB_PATH = DB_DIR / "devices.db"

_lock = threading.Lock()


def hash_token(token: str) -> str:
    """Hashes token using SHA-256 for secure storage at rest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DeviceDB:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with _lock, self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activation_codes (
                    code TEXT PRIMARY KEY,
                    agent_id TEXT,
                    mac_address TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    redeemed_by_device_id TEXT,
                    redeemed_at REAL
                );
            """)
            # Ensure mac_address column exists if table was created previously
            cols = [col[1] for col in conn.execute("PRAGMA table_info(activation_codes);").fetchall()]
            if "mac_address" not in cols:
                conn.execute("ALTER TABLE activation_codes ADD COLUMN mac_address TEXT;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    mac_address TEXT NOT NULL UNIQUE,
                    agent_id TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    hardware_model TEXT DEFAULT 'ESP32-S3',
                    firmware_version TEXT DEFAULT 'v2.1.8',
                    token_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'active',
                    online_status TEXT NOT NULL DEFAULT 'offline',
                    registered_at REAL NOT NULL,
                    last_seen REAL NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_rate_limits (
                    identifier TEXT PRIMARY KEY,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0
                );
            """)
            conn.commit()

    # =========================================================================
    # Rate Limiting & Brute-Force Protection
    # =========================================================================

    def check_rate_limit(self, identifier: str) -> Tuple[bool, int]:
        """Returns (is_allowed, remaining_lockout_seconds)."""
        now = time.time()
        with _lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT failed_attempts, locked_until FROM registration_rate_limits WHERE identifier = ?",
                (identifier,)
            ).fetchone()
            if row and row["locked_until"] > now:
                return False, int(row["locked_until"] - now)
        return True, 0

    def record_failed_attempt(self, identifier: str, max_attempts: int = 5, lockout_seconds: int = 300):
        now = time.time()
        with _lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT failed_attempts FROM registration_rate_limits WHERE identifier = ?",
                (identifier,)
            ).fetchone()
            attempts = (row["failed_attempts"] + 1) if row else 1
            locked_until = (now + lockout_seconds) if attempts >= max_attempts else 0
            conn.execute("""
                INSERT INTO registration_rate_limits (identifier, failed_attempts, locked_until)
                VALUES (?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    failed_attempts = ?,
                    locked_until = ?
            """, (identifier, attempts, locked_until, attempts, locked_until))
            conn.commit()

    def reset_failed_attempts(self, identifier: str):
        with _lock, self._get_connection() as conn:
            conn.execute("DELETE FROM registration_rate_limits WHERE identifier = ?", (identifier,))
            conn.commit()

    # =========================================================================
    # Activation Codes
    # =========================================================================

    def create_activation_code(self, agent_id: str, ttl_seconds: int = 300) -> Dict[str, Any]:
        """Generates a cryptographically secure 6-digit numeric activation code."""
        now = time.time()
        expires_at = now + ttl_seconds

        with _lock, self._get_connection() as conn:
            # Generate unique code
            for _ in range(10):
                code = f"{secrets.randbelow(1000000):06d}"
                existing = conn.execute(
                    "SELECT code FROM activation_codes WHERE code = ? AND expires_at > ?",
                    (code, now)
                ).fetchone()
                if not existing:
                    break
            else:
                code = f"{secrets.randbelow(1000000):06d}"

            conn.execute("""
                INSERT INTO activation_codes (code, agent_id, created_at, expires_at, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (code, agent_id, now, expires_at))
            conn.commit()

        logger.info("Generated activation code %s for agent %s (expires in %ds)", code, agent_id, ttl_seconds)
        return {
            "code": code,
            "agent_id": agent_id,
            "created_at": now,
            "expires_at": expires_at,
            "ttl_seconds": ttl_seconds,
            "status": "pending"
        }

    def get_or_create_code_for_device(self, mac_address: str, ttl_seconds: int = 300) -> str:
        """Returns existing valid pending activation code for a MAC or generates a fresh one."""
        now = time.time()
        expires_at = now + ttl_seconds
        with _lock, self._get_connection() as conn:
            row = conn.execute("""
                SELECT code FROM activation_codes
                WHERE mac_address = ? AND status = 'pending' AND expires_at > ?
                ORDER BY created_at DESC LIMIT 1
            """, (mac_address, now)).fetchone()
            if row:
                return row["code"]

            # Generate unique 6-digit code
            for _ in range(10):
                code = f"{secrets.randbelow(1000000):06d}"
                existing = conn.execute(
                    "SELECT code FROM activation_codes WHERE code = ? AND expires_at > ?",
                    (code, now)
                ).fetchone()
                if not existing:
                    break
            else:
                code = f"{secrets.randbelow(1000000):06d}"

            conn.execute("""
                INSERT INTO activation_codes (code, agent_id, mac_address, created_at, expires_at, status)
                VALUES (?, '', ?, ?, ?, 'pending')
            """, (code, mac_address, now, expires_at))
            conn.commit()

        logger.info("Generated ESP32 activation code %s for hardware MAC %s", code, mac_address)
        return code

    def is_device_activated(self, mac_address: str) -> bool:
        with _lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT device_id FROM devices WHERE mac_address = ? AND status = 'active'",
                (mac_address,)
            ).fetchone()
            return bool(row)

    def get_device_by_mac(self, mac_address: str) -> Optional[Dict[str, Any]]:
        with _lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE mac_address = ? AND status = 'active'",
                (mac_address,)
            ).fetchone()
            return dict(row) if row else None

    def bind_device_by_code(self, code: str, agent_id: str, device_name: Optional[str] = None) -> Dict[str, Any]:
        """User on console enters 6-digit code (spoken/printed by ESP32) and binds to selected Agent."""
        now = time.time()
        with _lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM activation_codes WHERE code = ?", (code,)).fetchone()
            if not row:
                raise ValueError("Invalid activation code.")

            if row["status"] == "redeemed":
                raise ValueError("Activation code has already been redeemed.")

            if row["expires_at"] <= now or row["status"] == "expired":
                conn.execute("UPDATE activation_codes SET status = 'expired' WHERE code = ?", (code,))
                conn.commit()
                raise ValueError("Activation code has expired.")

            mac_address = row["mac_address"]
            if not mac_address:
                # If code was generated from web without device MAC, generate virtual node MAC
                mac_address = f"30:ED:A0:{code[:2]}:{code[2:4]}:{code[4:6]}"

            device_id = f"dev_{secrets.token_hex(6)}"
            raw_token = secrets.token_urlsafe(32)
            token_digest = hash_token(raw_token)
            assigned_name = device_name or f"ESP32 ({mac_address[-5:]})"

            conn.execute("""
                INSERT INTO devices (
                    device_id, mac_address, agent_id, device_name,
                    hardware_model, firmware_version, token_hash,
                    status, online_status, registered_at, last_seen
                ) VALUES (?, ?, ?, ?, 'ESP32-S3', 'v2.1.8', ?, 'active', 'online', ?, ?)
                ON CONFLICT(mac_address) DO UPDATE SET
                    device_id = excluded.device_id,
                    agent_id = excluded.agent_id,
                    device_name = excluded.device_name,
                    token_hash = excluded.token_hash,
                    status = 'active',
                    online_status = 'online',
                    registered_at = excluded.registered_at,
                    last_seen = excluded.last_seen
            """, (device_id, mac_address, agent_id, assigned_name, token_digest, now, now))

            conn.execute("""
                UPDATE activation_codes
                SET status = 'redeemed', agent_id = ?, redeemed_by_device_id = ?, redeemed_at = ?
                WHERE code = ?
            """, (agent_id, device_id, now, code))
            conn.commit()

        logger.info("Successfully activated device %s (MAC: %s) with agent %s via code %s", device_id, mac_address, agent_id, code)
        return {
            "device_id": device_id,
            "device_token": raw_token,
            "mac_address": mac_address,
            "agent_id": agent_id,
            "device_name": assigned_name,
            "status": "active"
        }

    def get_activation_status(self, code: str) -> Dict[str, Any]:
        now = time.time()
        with _lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM activation_codes WHERE code = ?", (code,)).fetchone()
            if not row:
                return {"status": "not_found", "code": code}

            if row["status"] == "pending" and row["expires_at"] <= now:
                conn.execute("UPDATE activation_codes SET status = 'expired' WHERE code = ?", (code,))
                conn.commit()
                return {"status": "expired", "code": code, "agent_id": row["agent_id"]}

            res = {
                "code": row["code"],
                "agent_id": row["agent_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "remaining_seconds": max(0, int(row["expires_at"] - now)),
            }
            if row["status"] == "redeemed" and row["redeemed_by_device_id"]:
                dev = conn.execute(
                    "SELECT device_id, mac_address, device_name, hardware_model, firmware_version, status, online_status "
                    "FROM devices WHERE device_id = ?",
                    (row["redeemed_by_device_id"],)
                ).fetchone()
                if dev:
                    res["device"] = dict(dev)
            return res

    # =========================================================================
    # Device Registration & Authentication
    # =========================================================================

    def register_device_with_code(
        self,
        code: str,
        mac_address: str,
        device_name: Optional[str] = None,
        hardware_model: str = "ESP32-S3",
        firmware_version: str = "v2.1.8"
    ) -> Dict[str, Any]:
        """Validates code, creates device record, and returns plaintext token (only once)."""
        now = time.time()
        with _lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM activation_codes WHERE code = ?", (code,)).fetchone()
            if not row:
                raise ValueError("Invalid activation code.")

            if row["status"] == "redeemed":
                raise ValueError("Activation code has already been redeemed.")

            if row["expires_at"] <= now or row["status"] == "expired":
                conn.execute("UPDATE activation_codes SET status = 'expired' WHERE code = ?", (code,))
                conn.commit()
                raise ValueError("Activation code has expired.")

            agent_id = row["agent_id"]

            # Generate high-entropy token and device id
            device_id = f"dev_{secrets.token_hex(6)}"
            raw_token = secrets.token_urlsafe(32)
            token_digest = hash_token(raw_token)

            assigned_name = device_name or f"ESP32 ({mac_address[-5:]})"

            # Insert or replace device record for this MAC
            conn.execute("""
                INSERT INTO devices (
                    device_id, mac_address, agent_id, device_name,
                    hardware_model, firmware_version, token_hash,
                    status, online_status, registered_at, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 'online', ?, ?)
                ON CONFLICT(mac_address) DO UPDATE SET
                    device_id = excluded.device_id,
                    agent_id = excluded.agent_id,
                    device_name = excluded.device_name,
                    hardware_model = excluded.hardware_model,
                    firmware_version = excluded.firmware_version,
                    token_hash = excluded.token_hash,
                    status = 'active',
                    online_status = 'online',
                    registered_at = excluded.registered_at,
                    last_seen = excluded.last_seen
            """, (
                device_id, mac_address, agent_id, assigned_name,
                hardware_model, firmware_version, token_digest,
                now, now
            ))

            # Mark activation code redeemed
            conn.execute("""
                UPDATE activation_codes
                SET status = 'redeemed', redeemed_by_device_id = ?, redeemed_at = ?
                WHERE code = ?
            """, (device_id, now, code))

            conn.commit()

        logger.info("Successfully registered device %s (MAC: %s) with agent %s", device_id, mac_address, agent_id)
        return {
            "device_id": device_id,
            "device_token": raw_token,  # returned plaintext to client exactly once
            "mac_address": mac_address,
            "agent_id": agent_id,
            "device_name": assigned_name,
            "status": "active"
        }

    def authenticate_device(self, raw_token: str) -> Optional[Dict[str, Any]]:
        """Verifies bearer token hash against active devices."""
        token_digest = hash_token(raw_token)
        with _lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE token_hash = ? AND status = 'active'",
                (token_digest,)
            ).fetchone()
            if row:
                return dict(row)
        return None

    def update_heartbeat(self, raw_token: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        token_digest = hash_token(raw_token)
        with _lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT device_id, mac_address, agent_id FROM devices WHERE token_hash = ? AND status = 'active'",
                (token_digest,)
            ).fetchone()
            if not row:
                return None

            conn.execute(
                "UPDATE devices SET last_seen = ?, online_status = 'online' WHERE token_hash = ?",
                (now, token_digest)
            )
            conn.commit()
            return {"device_id": row["device_id"], "mac_address": row["mac_address"], "last_seen": now}

    def unbind_device_by_token(self, raw_token: str) -> bool:
        token_digest = hash_token(raw_token)
        with _lock, self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE devices SET status = 'revoked', online_status = 'offline' WHERE token_hash = ?",
                (token_digest,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def unbind_device_by_identifier(self, identifier: str) -> bool:
        """Unbinds and revokes credentials by device_id or mac_address."""
        with _lock, self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE devices
                SET status = 'revoked', online_status = 'offline'
                WHERE device_id = ? OR mac_address = ?
            """, (identifier, identifier))
            conn.commit()
            return cursor.rowcount > 0

    def list_authenticated_devices(self) -> List[Dict[str, Any]]:
        now = time.time()
        with _lock, self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM devices WHERE status = 'active' ORDER BY registered_at DESC").fetchall()
            devices = []
            for r in rows:
                is_online = (now - r["last_seen"]) < 120  # Online if seen within last 2 minutes
                devices.append({
                    "id": r["device_id"],
                    "device_id": r["device_id"],
                    "mac_address": r["mac_address"],
                    "agent_id": r["agent_id"],
                    "name": r["device_name"],
                    "hardware_model": r["hardware_model"],
                    "firmware_version": r["firmware_version"],
                    "registration_status": "authenticated",
                    "status": "online" if is_online else "offline",
                    "registered_at": r["registered_at"],
                    "last_seen_ts": r["last_seen"],
                    "last_seen": "Just now" if (now - r["last_seen"]) < 60 else f"{int((now - r['last_seen'])/60)}m ago"
                })
            return devices


device_db = DeviceDB()
