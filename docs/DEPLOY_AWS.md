# Hướng Dẫn Triển Khai XiaoZhi AI Lên AWS (Amazon Web Services)

Tài liệu này hướng dẫn chi tiết cách đưa toàn bộ hệ thống XiaoZhi AI lên máy chủ đám mây AWS với hiệu năng cao, bảo mật và chi phí tối ưu nhất.

---

## 1. Kiến trúc hệ thống trên AWS

Khi triển khai trên AWS, thiết bị ESP32 ở nhà sẽ kết nối qua Internet. Vì vậy, ta dựng **Nginx Reverse Proxy + SSL Let's Encrypt** để bảo mật kết nối qua đường truyền `wss://` (WebSocket Secure):

```
[ ESP32 tại nhà ]
       │  (Internet qua Wi-Fi / wss://xiaozhi.yourdomain.com)
       ▼
[ AWS EC2 Instance: g4dn.xlarge (All-in-One) ]
   ├── Nginx (Port 443 SSL / Let's Encrypt)
   │     ├── Proxy /ws  ──> XiaoZhi Server (Port 8000)
   │     └── Proxy /v1  ──> AI Gateway (Port 8080 - Bảo mật bằng API Key)
   │
   ├── XiaoZhi Server (xinnan-tech/xiaozhi-esp32-server)
   └── Cụm AI Backend (Chạy trên cùng máy -> Latency nội bộ 0ms):
         ├── Ollama LLM (NVIDIA T4 16GB VRAM)
         ├── Faster-Whisper STT (4 vCPU)
         └── Piper TTS (4 vCPU)
```

> **Lợi ích của mô hình All-in-One trên AWS:** XiaoZhi Server gọi sang cụm AI qua mạng nội bộ `localhost` (độ trễ = 0ms), chỉ tốn tiền thuê đúng 1 máy ảo EC2 duy nhất.

---

## 2. Thông số máy ảo EC2 khuyến nghị

| Thông số | Giá trị khuyến nghị | Ghi chú |
| :--- | :--- | :--- |
| **Instance Type** | **`g4dn.xlarge`** | 4 vCPU, 16GB RAM, **1x NVIDIA T4 GPU (16GB VRAM)** |
| **Hệ điều hành (AMI)** | **Ubuntu Server 22.04 LTS** *(x86_64)* | Bản ổn định và tương thích tốt nhất |
| **Dung lượng ổ đĩa (EBS)** | **60 GB - 80 GB gp3** | Đủ chứa Docker images, checkpoints model và cache OS |
| **Chi phí On-Demand** | ~$0.526 / giờ (~$380/tháng nếu bật 24/7) | Giá thông thường |
| **Chi phí Spot Instance** | **~$0.15 - $0.20 / giờ** | **Tiết kiệm tới 70%** (khuyên dùng khi thử nghiệm) |

---

## 3. Bước 1: Khởi tạo EC2 và Cấu hình Security Group

### 3.1. Tạo EC2 trên AWS Console
1. Đăng nhập AWS Console $\rightarrow$ dịch vụ **EC2** $\rightarrow$ **Launch Instance**.
2. **Name**: `xiaozhi-ai-server`.
3. **AMI**: Chọn **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type**.
4. **Instance Type**: Chọn **`g4dn.xlarge`**.
5. **Key pair**: Tạo hoặc chọn key pair `.pem` của bạn để SSH.
6. **Storage**: Đổi từ `8 GiB` mặc định thành **`60 GiB gp3`**.

### 3.2. Cấu hình Security Group (Tường lửa)
Thêm các Inbound Rules sau:

| Type | Port Range | Source | Mục đích |
| :--- | :--- | :--- | :--- |
| **SSH** | `22` | `My IP` (hoặc `0.0.0.0/0`) | Đăng nhập quản trị máy chủ |
| **HTTP** | `80` | `0.0.0.0/0` | Dùng để Certbot xác thực cấp chứng chỉ SSL |
| **HTTPS** | `443` | `0.0.0.0/0` | Cổng kết nối an toàn chính cho ESP32 (`wss://`) |

---

## 4. Bước 2: Cài đặt Driver NVIDIA & Docker trên EC2

SSH vào máy chủ EC2:
```bash
ssh -i your-key.pem ubuntu@<PUBLIC_IP_EC2>
```

Chạy script cài đặt nhanh trọn gói NVIDIA Driver + Docker + NVIDIA Container Toolkit:

```bash
# 1. Cập nhật hệ thống
sudo apt update && sudo apt upgrade -y

# 2. Cài đặt NVIDIA Driver
sudo apt install -y nvidia-driver-535 nvidia-utils-535

# 3. Cài đặt Docker & Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 4. Cài đặt NVIDIA Container Toolkit (để Docker dùng được GPU T4)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 5. Khởi động lại máy để nạp Driver NVIDIA
sudo reboot
```

Sau 1 phút, SSH lại vào máy và gõ:
```bash
nvidia-smi
```
*(Nếu hiện bảng thông tin GPU **Tesla T4 16GB** là bạn đã cấu hình phần cứng thành công 100%)*.

---

## 5. Bước 3: Đưa Code lên EC2 & Khởi chạy

Trên máy EC2, tạo thư mục dự án:
```bash
mkdir -p ~/xiaozhi-backend
cd ~/xiaozhi-backend
```

Bạn có thể clone repo Git của bạn hoặc dùng `scp` để copy các thư mục (`faster-whisper`, `piper`, `gateway`, `docker-compose.yml`, `scripts/init_models.sh`) từ máy tính lên EC2:

```bash
# Trên máy tính cá nhân của bạn:
scp -i your-key.pem -r * ubuntu@<PUBLIC_IP_EC2>:~/xiaozhi-backend/
```

Trên máy chủ EC2, cấp quyền thực thi và khởi chạy:
```bash
cd ~/xiaozhi-backend
chmod +x scripts/init_models.sh

# 1. Khởi chạy 4 container AI
docker compose up -d --build

# 2. Tải model tiếng Việt và Qwen LLM
./scripts/init_models.sh
```

---

## 6. Bước 4: Cài đặt XiaoZhi Server & Nginx SSL trên EC2

### 6.1. Khởi chạy XiaoZhi Server (kết nối nội bộ tới Gateway 8080)
Tạo file `config.yaml` cho XiaoZhi server ngay trên EC2:
```yaml
selected_module:
  ASR: OpenAIASR
  LLM: OpenAILLM
  TTS: OpenAITTS

ASR:
  OpenAIASR:
    type: openai
    base_url: http://127.0.0.1:8080/v1
    api_key: sk-xiaozhi-local-secret
    model_name: small
    language: vi

LLM:
  OpenAILLM:
    type: openai
    base_url: http://127.0.0.1:8080/v1
    api_key: sk-xiaozhi-local-secret
    model_name: qwen2.5:3b-instruct

TTS:
  OpenAITTS:
    type: openai
    api_url: http://127.0.0.1:8080/v1/audio/speech
    api_key: sk-xiaozhi-local-secret
    model: tts-1
    voice: vi_VN-vais1000-medium

server:
  port: 8000
  listen: 127.0.0.1
```

Chạy XiaoZhi Server qua Docker:
```bash
docker run -d \
  --name xiaozhi-server \
  --network host \
  --restart always \
  -v $(pwd)/config.yaml:/app/data/.config.yaml:ro \
  ghcr.io/xinnan-tech/xiaozhi-esp32-server:latest
```

### 6.2. Cấu hình Nginx + SSL Let's Encrypt (Cổng 443 an toàn)
Cài đặt Nginx và Certbot:
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Trỏ tên miền (ví dụ `xiaozhi.yourdomain.com`) về Public IP của EC2. Sau đó cấu hình file `/etc/nginx/sites-available/xiaozhi`:

```nginx
server {
    server_name xiaozhi.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

Kích hoạt site và cấp SSL tự động:
```bash
sudo ln -s /etc/nginx/sites-available/xiaozhi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d xiaozhi.yourdomain.com
```

Lúc này, trên thiết bị ESP32 bạn chỉ cần điền đường dẫn WebSocket:
```
wss://xiaozhi.yourdomain.com/
```

---

## 7. Mẹo tối ưu chi phí AWS (Cực kỳ quan trọng)

1. **Gán Elastic IP tĩnh miễn phí**: Gán 1 Elastic IP cho EC2 để IP không bị đổi mỗi khi bạn Stop/Start máy ảo.
2. **Dùng AWS Spot Instance**: Chọn loại Spot khi launch instance giúp giảm giá thuê từ `$0.52/h` xuống còn **`$0.15/h`** (tiết kiệm 70%).
3. **Tắt máy khi không sử dụng**: 
   - Khi không dùng, vào AWS Console bấm **Stop Instance** (chỉ tốn ~\$5/tháng tiền lưu trữ ổ đĩa EBS 60GB).
   - Có thể thiết lập AWS EventBridge tự động tắt EC2 lúc 0h đêm để tránh quên gây phát sinh chi phí.
