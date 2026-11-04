# Hướng Dẫn Nhanh Cho Máy B (XiaoZhi Server - Linux)

Gói cài đặt này dùng để triển khai **XiaoZhi ESP32 Server** trên Máy B và kết nối tới cụm AI Gateway trên Máy A.

---

## 3 Bước Triển Khai:

### Bước 1: Giải nén và vào thư mục
```bash
unzip xiaozhi_machine_b.zip -d xiaozhi-server
cd xiaozhi-server
chmod +x start.sh
```

### Bước 2: Điền IP của Máy A
Mở file `config.yaml`:
```bash
nano config.yaml
```
Thay thế chữ `IP_MAY_A` bằng IP mạng LAN thực tế của Máy A (ví dụ: `192.168.1.150`), sau đó lưu lại (`Ctrl + O`, `Enter`, `Ctrl + X`).

### Bước 3: Khởi chạy
```bash
./start.sh
```

- Server sẽ tự động kéo Docker image và bật cổng WebSocket `8000`.
- Màn hình sẽ in ra đường dẫn WebSocket (ví dụ `ws://192.168.1.50:8000/`) để nạp vào thiết bị ESP32.
