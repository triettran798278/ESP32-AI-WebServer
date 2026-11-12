# Hướng Dẫn Kết Nối Tasmota ↔ ThingsBoard (2 Chiều)

*Cấu hình cố định qua MQTT Broker trung gian (`broker.emqx.io`), không đổi Port theo giờ và hỗ trợ điều khiển 2 chiều.*

---

## 1. Thông Tin Kết Nối

- **Web ThingsBoard:** `https://codehelpers.tech`
- **MQTT Host:** `broker.emqx.io`
- **MQTT Port:** `1883`
- **User / Password:** *(để trống)*
- **Topic:** `sensor1` *(hoặc tên device bạn muốn hiển thị trên ThingsBoard)*
- **Full Topic:** `tbch_8x4k/%prefix%/%topic%/`

> **Lưu ý bảo mật:** `broker.emqx.io:1883` là MQTT broker công cộng dùng để test/demo nhanh (không có mật khẩu). Tiền tố `tbch_8x4k` giúp tách dữ liệu khỏi người khác và khớp sẵn với ThingsBoard, nhưng **không dùng để truyền dữ liệu nhạy cảm** (mật khẩu, token, thông tin riêng tư).

---

## 2. Cấu Hình Trên Tasmota

### Bước 1: Nhập thông số MQTT (`Configuration → Configure MQTT`)
- **Host:** `broker.emqx.io`
- **Port:** `1883`
- **User:** *(xóa trắng / để trống)*
- **Password:** *(xóa trắng / để trống)*
- **Topic:** `sensor1` *(đổi tên khác nếu kết nối nhiều mạch, ví dụ `sensor2` — ThingsBoard sẽ tự tạo device tương ứng)*
- **Full Topic:** `tbch_8x4k/%prefix%/%topic%/`
- Bấm **Save** (Tasmota sẽ tự khởi động lại).

### Bước 2: Tắt Rule cũ (nếu trước đó đã dán `Rule1` / `Rule2`)
Nếu mạch mới flash sạch thì **bỏ qua bước này** (không cần viết Rule nào cả).
Nếu trước đó bạn từng cài `Rule1` / `Rule2` để đẩy vào `v1/devices/me/telemetry`, mở **Consoles → Console** và chạy:
```text
Rule1 0
Rule2 0
```

---

## 3. Kiểm Tra Kết Nối 2 Chiều Trên ThingsBoard

1. Mở `https://codehelpers.tech` → **Entities → Devices** → chọn `sensor1` (hoặc device mới vừa tự tạo).
2. **Chiều lên (Tasmota → ThingsBoard):**
   - Trong tab **Latest telemetry** sẽ tự hiện: `online`, `power`, `POWER`, `rssi`, cùng các trường cảm biến (ví dụ `temperature`, `humidity`, `pressure`, `illuminance` và khóa chi tiết `<TenCamBien>_<Truong>`).
   - Trong tab **Attributes → Client attributes** có `tasmotaTopic`, `online`, `power`, `lwt`.
3. **Chiều xuống (ThingsBoard → Tasmota):**
   - **Qua Shared Attributes:** thêm hoặc cập nhật shared attribute `power` (`true` / `false`) hoặc `POWER` (`"ON"` / `"OFF"`).
   - **Qua Dashboard Widget / RPC:** dùng RPC method `setValue`, `setPower` hoặc `power` với giá trị `true` / `false` / `"ON"` / `"OFF"` / `"TOGGLE"`.
   - Khi Tasmota nhận lệnh đổi trạng thái, ThingsBoard sẽ tự cập nhật lại telemetry `power` / `POWER` tương ứng.
