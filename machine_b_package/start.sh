#!/usr/bin/env bash
set -e

echo "=== KHOI DONG XIAOZHI SERVER (MAY B) ==="

# 1. Kiem tra file config.yaml da doi IP chua
if grep -q "IP_MAY_A" config.yaml; then
    echo "[CANH BAO] Ban chua doi IP_MAY_A trong file config.yaml!"
    echo "Vui long mo file config.yaml (nano config.yaml) va thay the 'IP_MAY_A' bang IP thuc te cua May A."
    exit 1
fi

# 2. Tao thu muc tmp
mkdir -p tmp

# 3. Mo port tren tuong lua Linux neu co UFW
if command -v ufw >/dev/null 2>&1; then
    echo "Dang kiem tra mo port 8000 tren UFW..."
    sudo ufw allow 8000/tcp >/dev/null 2>&1 || true
fi

# 4. Khoi chay Docker
echo "Dang khoi chay Docker Compose..."
docker compose up -d

# 5. In dia chi WebSocket cho ESP32
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "================================================================"
echo " [THANH CONG] XiaoZhi Server da hoat dong!"
echo " URL ket noi WebSocket cho ESP32: ws://${LOCAL_IP}:8000/"
echo "================================================================"
echo "Dang theo doi log (Nhan Ctrl+C de thoat log, container van chay ngam):"
docker compose logs -f
