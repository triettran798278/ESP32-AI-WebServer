"""Local console accounts and revocable sessions."""

import argparse
from contextlib import contextmanager
import getpass
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIR = Path(os.getenv('PLATFORM_DATA_DIR', '/app/data' if os.path.exists('/app') else './data'))
SESSION_SECONDS = 12 * 60 * 60
logger = logging.getLogger('platform_bridge.accounts')


def _password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class AccountStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else DATA_DIR / 'accounts.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, salt TEXT NOT NULL, password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    address TEXT NOT NULL, attempted_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS login_attempts_address ON login_attempts(address, attempted_at);
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL, data TEXT NOT NULL,
                    FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires_at REAL NOT NULL,
                    FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE
                );
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=15)
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _credentials(username, password):
        if not username or username != username.strip() or len(username) > 128:
            raise ValueError('Invalid username')
        if len(password) < 12 or len(password) > 1024:
            raise ValueError('Password must contain 12 to 1024 characters')
        salt = secrets.token_bytes(16)
        return salt.hex(), _password_hash(password, salt)

    def user_exists(self, username):
        with self.connect() as conn:
            return conn.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone() is not None

    def create_user(self, username, password):
        salt, digest = self._credentials(username, password)
        try:
            with self.connect() as conn:
                conn.execute('INSERT INTO users VALUES (?, ?, ?)', (username, salt, digest))
        except sqlite3.IntegrityError as exc:
            raise ValueError('Account already exists') from exc

    def reset_password(self, username, password):
        salt, digest = self._credentials(username, password)
        with self.connect() as conn:
            result = conn.execute('UPDATE users SET salt = ?, password_hash = ? WHERE username = ?', (salt, digest, username))
            if not result.rowcount:
                raise ValueError('Account does not exist')
            conn.execute('DELETE FROM sessions WHERE username = ?', (username,))

    def login(self, username, password):
        with self.connect() as conn:
            row = conn.execute('SELECT salt, password_hash FROM users WHERE username = ?', (username,)).fetchone()
            salt = bytes.fromhex(row[0]) if row else bytes(16)
            digest = _password_hash(password[:1024], salt)
            if len(password) > 1024 or not row or not hmac.compare_digest(digest, row[1]):
                return None
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT salt, password_hash FROM users WHERE username = ?', (username,)).fetchone()
            if current != row:
                return None
            token = secrets.token_urlsafe(32)
            conn.execute('DELETE FROM sessions WHERE expires_at <= ?', (time.time(),))
            conn.execute('INSERT INTO sessions VALUES (?, ?, ?)', (_token_hash(token), username, time.time() + SESSION_SECONDS))
            return token

    def session_user(self, token):
        if not token:
            return None
        with self.connect() as conn:
            row = conn.execute('SELECT username FROM sessions WHERE token_hash = ? AND expires_at > ?',
                               (_token_hash(token), time.time())).fetchone()
            return row[0] if row else None

    def record_attempt(self, address):
        now = time.time()
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM login_attempts WHERE attempted_at <= ?', (now - 300,))
            count = conn.execute('SELECT COUNT(*) FROM login_attempts WHERE address = ?', (address,)).fetchone()[0]
            if count >= 10:
                return False
            conn.execute('INSERT INTO login_attempts VALUES (?, ?)', (address, now))
            return True

    def list_agents(self, username):
        with self.connect() as conn:
            rows = conn.execute('SELECT data FROM agents WHERE username = ?', (username,)).fetchall()
            return [json.loads(row[0]) for row in rows]

    def get_agent_by_id(self, agent_id):
        with self.connect() as conn:
            row = conn.execute('SELECT data FROM agents WHERE id = ?', (agent_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def get_agent(self, username, agent_id):
        with self.connect() as conn:
            row = conn.execute('SELECT data FROM agents WHERE username = ? AND id = ?', (username, agent_id)).fetchone()
            return json.loads(row[0]) if row else None

    def put_agent(self, username, agent):
        with self.connect() as conn:
            result = conn.execute("""INSERT INTO agents (id, username, data) VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET data = excluded.data WHERE username = excluded.username""",
                (agent['id'], username, json.dumps(agent, ensure_ascii=False)))
            if not result.rowcount:
                raise ValueError('Agent belongs to another user')

    @contextmanager
    def edit_agent(self, username, agent_id):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT data FROM agents WHERE username = ? AND id = ?', (username, agent_id)).fetchone()
            if not row:
                raise ValueError('Agent does not exist')
            agent = json.loads(row[0])
            yield agent
            conn.execute('UPDATE agents SET data = ? WHERE username = ? AND id = ?',
                         (json.dumps(agent, ensure_ascii=False), username, agent_id))

    def append_chat(self, agent_id, entry):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT data FROM agents WHERE id = ?', (agent_id,)).fetchone()
            if not row:
                return
            agent = json.loads(row[0])
            agent['chats'] = (agent.get('chats', []) + [entry])[-50:]
            conn.execute('UPDATE agents SET data = ? WHERE id = ?', (json.dumps(agent, ensure_ascii=False), agent_id))

    def delete_agent(self, username, agent_id):
        with self.connect() as conn:
            result = conn.execute('DELETE FROM agents WHERE username = ? AND id = ?', (username, agent_id))
            return bool(result.rowcount)

    def logout(self, token):
        if token:
            with self.connect() as conn:
                conn.execute('DELETE FROM sessions WHERE token_hash = ?', (_token_hash(token),))


def _validated_tb_host(raw_host):
    if not raw_host:
        return ''
    try:
        parsed = urlsplit(raw_host)
        if (parsed.scheme in ('http', 'https') and parsed.hostname and parsed.username is None
                and parsed.password is None and parsed.path in ('', '/')
                and not parsed.query and not parsed.fragment):
            hostname = f'[{parsed.hostname.lower()}]' if ':' in parsed.hostname else parsed.hostname.lower()
            return f'{parsed.scheme}://{hostname}' + (f':{parsed.port}' if parsed.port is not None else '')
    except (ValueError, TypeError):
        pass
    logger.warning('Ignoring invalid THINGSBOARD_HOST during agent bootstrap')
    return ''


def bootstrap_from_env(store, env=None):
    """Idempotently create an initial console account and starter agent from env vars."""
    env = os.environ if env is None else env
    username = (env.get('CONSOLE_USERNAME') or '').strip()
    password = env.get('CONSOLE_PASSWORD') or ''
    if not username or not password:
        return {'created_user': False, 'created_agent': False}

    created_user = False
    if not store.user_exists(username):
        try:
            store.create_user(username, password)
            created_user = True
            logger.info('Bootstrapped console account %r from environment', username)
        except ValueError as exc:
            if 'already exists' not in str(exc):
                logger.warning('Skipping CONSOLE_USERNAME bootstrap for %r: %s', username, exc)
                return {'created_user': False, 'created_agent': False, 'error': str(exc)}

    if not store.list_agents(username):
        tb_host = _validated_tb_host((env.get('THINGSBOARD_HOST') or '').strip().rstrip('/'))
        tb_key = (env.get('THINGSBOARD_API_KEY') or '').strip()
        agent_id = 'agent_' + hashlib.sha256(f'bootstrap:{username}'.encode()).hexdigest()[:16]
        starter_agent = {
            'id': agent_id,
            'name': 'Smart Home Assistant',
            'role': 'Nova',
            'status': 'online',
            'language': 'vi',
            'tool_policy': 'full_control',
            'prompt': (
                'Bạn là Nova, trợ lý giọng nói thông minh cho gia đình. '
                'Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên.'
            ),
            'tts': {'voice': 'vi_VN-vais1000-medium', 'speed': 'standard'},
            'llm': {'model': 'qwen2.5:3b-instruct'},
            'integrations': {
                'thingsboard': {
                    'host': tb_host,
                    'api_key': tb_key,
                    'display_name': 'ThingsBoard IoT',
                    'timeout_seconds': 10.0,
                }
            },
            'devices': [],
            'chats': [],
            'memories': [],
        }
        store.put_agent(username, starter_agent)
        logger.info('Seeded default agent %s for %r', agent_id, username)
        return {'created_user': created_user, 'created_agent': True, 'username': username, 'agent_id': agent_id}

    return {'created_user': created_user, 'created_agent': False, 'username': username}


def main():
    parser = argparse.ArgumentParser(description='Manage platform console accounts')
    parser.add_argument('action', choices=['create', 'reset-password', 'bootstrap'])
    parser.add_argument('username', nargs='?')
    args = parser.parse_args()
    store = AccountStore()
    if args.action == 'bootstrap':
        result = bootstrap_from_env(store)
        print(
            f"Bootstrap complete (created_user={result['created_user']}, "
            f"created_agent={result['created_agent']})"
        )
        return
    if not args.username:
        parser.error('username is required')
    password = getpass.getpass('Password: ')
    if password != getpass.getpass('Confirm password: '):
        parser.error('Passwords do not match')
    try:
        if args.action == 'create':
            store.create_user(args.username, password)
        else:
            store.reset_password(args.username, password)
    except ValueError as exc:
        parser.error(str(exc))
    print('Account updated')


if __name__ == '__main__':
    main()
