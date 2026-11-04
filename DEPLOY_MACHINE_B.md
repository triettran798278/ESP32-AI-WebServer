# Hướng Dẫn Deploy & Cấu Hình XiaoZhi Server Trên Máy B (Linux Docker)

Tài liệu này được tối ưu riêng cho **Máy B chạy Linux** (Ubuntu, Debian, Fedora, Arch, Raspberry Pi OS,...) làm Gateway kết nối tới **Máy A chạy Windows/AI Backend** (Ryzen 7 8845HS + GPU).

---

## 1. Mô hình kết nối hệ thống (Unified Gateway - 1 Port & 1 Key)

```
[ Thiết bị ESP32 ]
        │  (WebSocket / Wi-Fi)
        ▼
[ MÁY B (LINUX): XiaoZhi Server ]
        │
        │  (Duy nhất 1 cổng 8080 & 1 API Key: sk-xiaozhi-local-secret)
        ▼
[ MÁY A: AI Unified Gateway (Port 8080) ]
        ├── /v1/chat/completions       ──> Chuyển tiếp tới Ollama GPU
        ├── /v1/audio/transcriptions   ──> Chuyển tiếp tới Faster-Whisper CPU
        └── /v1/audio/speech           ──> Chuyển tiếp tới Piper TTS CPU
```

---

## 2. Bước 1: Kiểm tra kết nối từ Máy B sang Gateway Máy A

Giả sử IP mạng LAN của Máy A là `192.168.1.150`:
```bash
export AI_NODE_IP="192.168.1.150"
export API_KEY="sk-xiaozhi-local-secret"

# 1. Kiểm tra Gateway Health (không cần key)
curl -s "http://${AI_NODE_IP}:8080/health"

# 2. Kiểm tra gọi qua Gateway (kèm API Key)
curl -s -H "Authorization: Bearer ${API_KEY}" "http://${AI_NODE_IP}:8080/v1/models"
```
*(Nếu thành công, bạn sẽ nhận được JSON danh sách model và trạng thái `gateway: unified`)*.

---

## 3. Bước 2: Chuẩn bị thư mục & Docker trên Máy B

Nếu tài khoản hiện tại chưa chạy được Docker không cần `sudo`:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

Tạo thư mục dự án:
```bash
mkdir -p ~/xiaozhi-server/tmp
cd ~/xiaozhi-server
```

---

## 4. Bước 3: Tạo file `config.yaml` (Cực kỳ ngắn gọn)

Nhờ có Gateway, tất cả ASR, LLM, TTS trên Máy B đều trỏ về **cùng 1 Base URL (`:8080/v1`)** và **1 API Key**:

```bash
cat << 'EOF' > config.yaml
selected_module:
  ASR: OpenAIASR
  LLM: OpenAILLM
  TTS: OpenAITTS

ASR:
  OpenAIASR:
    type: openai
    base_url: http://192.168.1.150:8080/v1
    api_key: sk-xiaozhi-local-secret
    model_name: small
    language: vi
    output_dir: tmp/

LLM:
  OpenAILLM:
    type: openai
    base_url: http://192.168.1.150:8080/v1
    api_key: sk-xiaozhi-local-secret
    model_name: qwen2.5:3b-instruct
    temperature: 0.7

TTS:
  OpenAITTS:
    type: openai
    api_url: http://192.168.1.150:8080/v1/audio/speech
    api_key: sk-xiaozhi-local-secret
    model: tts-1
    voice: vi_VN-vais1000-medium
    response_format: wav
    speed: 1.0
    output_dir: tmp/

server:
  port: 8000
  listen: 0.0.0.0
EOF
```
*(Nhớ đổi `192.168.1.150` thành IP thực tế của Máy A)*.

---

## 5. Bước 4: Tạo `docker-compose.yml` & Khởi chạy

Tạo file `docker-compose.yml`:
```bash
cat << 'EOF' > docker-compose.yml
services:
  xiaozhi-server:
    image: ghcr.io/xinnan-tech/xiaozhi-esp32-server:latest
    container_name: xiaozhi-server
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/data/.config.yaml:ro
      - ./tmp:/app/tmp
    environment:
      - TZ=Asia/Ho_Chi_Minh
EOF
```

Khởi chạy container:
```bash
docker compose up -d
docker compose logs -f
```

---

## 6. Bước 5: Mở Firewall trên Linux (Nếu Máy B bật UFW/Firewalld)

Để thiết bị ESP32 kết nối được vào port `8000` của Máy B:

- **Nếu dùng UFW (Ubuntu/Debian):**
  ```bash
  sudo ufw allow 8000/tcp
  sudo ufw reload
  ```
- **Nếu dùng Firewalld (CentOS/RHEL/Fedora):**
  ```bash
  sudo firewall-cmd --permanent --add-port=8000/tcp
  sudo firewall-cmd --reload
  ```

---

## 7. Bước 6: Cấu hình trên thiết bị ESP32

- URL WebSocket kết nối: `ws://<IP_MÁY_B>:8000/` (thay `<IP_MÁY_B>` bằng IP lấy được ở mục 2.1).
- ESP32 và Máy B cùng kết nối chung một mạng WiFi/Router.

---

## 8. Xử lý sự cố thường gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| `curl` từ Máy B sang Máy A port 8080 báo `timed out` | Windows Firewall trên Máy A chặn cổng | Chạy lệnh mở port trên PowerShell (Admin) Máy A:<br>`New-NetFirewallRule -DisplayName "XiaoZhi Gateway" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow` |
| HTTP 401 Unauthorized | Sai hoặc thiếu API Key | Kiểm tra lại `api_key: sk-xiaozhi-local-secret` trong `config.yaml` |
| ESP32 không kết nối được WebSocket | Máy B Linux bật tường lửa chặn port 8000 | Chạy `sudo ufw allow 8000/tcp` trên Máy B |


