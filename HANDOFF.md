# XiaoZhi Full-Local AI Backend — Tài Liệu Bàn Giao Kỹ Thuật (Technical Handoff)

*Tài liệu này tổng hợp toàn bộ hiện trạng kiến trúc, mã nguồn, thông số vận hành và hướng dẫn kết nối của cụm Backend AI Full-Local phục vụ thiết bị XiaoZhi ESP32.*

---

## 1. Mục Tiêu & Tổng Quan Hệ Thống

Dự án cung cấp một cụm backend AI chạy hoàn toàn nội bộ (Full-Local 100%), không phụ thuộc vào bất kỳ dịch vụ đám mây bên ngoài nào. Hệ thống xử lý trọn vẹn luồng đàm thoại thông minh cho thiết bị **XiaoZhi ESP32**:
1. **STT (Speech-to-Text)**: Nhận giọng nói tiếng Việt từ microphone thiết bị qua Faster-Whisper.
2. **LLM & Tool Calling**: Xử lý ngữ nghĩa, suy luận và gọi công cụ (Function/Tool Calling) bằng model `qwen2.5:3b-instruct` kết hợp **Model Context Protocol (MCP)**.
3. **TTS (Text-to-Speech)**: Tổng hợp câu trả lời tự nhiên thành âm thanh tiếng Việt bằng Piper TTS siêu tốc để phát lại qua loa thiết bị.
4. **Cổng Hợp Nhất (Unified Gateway)**: Cung cấp 1 điểm truy cập duy nhất chuẩn OpenAI REST API trên **Cổng 8080** với 1 API Key bảo mật.

---

## 2. Kiến Trúc Cụm 5 Containers (Docker Compose)

Toàn bộ hệ thống được container hóa và điều phối qua [`docker-compose.yml`](file:///docker-compose.yml):

| Service | Container Name | Port Mapping | Môi trường / Phần cứng | Nhiệm vụ chính |
| :--- | :--- | :--- | :--- | :--- |
| **`gateway`** | `gateway` | `8080:8080` | Python 3.11-slim (CPU) | Cổng trung tâm điều hướng request, kiểm tra API Key |
| **`mcp-gateway`** | `mcp-gateway` | `8008:8008` | Python 3.11-slim (CPU) | MCP Client Bridge kết nối Ollama & MCP Server |
| **`ollama`** | `ollama` | `11434:11434` | NVIDIA GPU (CUDA) | Chạy LLM `qwen2.5:3b-instruct` độc chiếm VRAM |
| **`faster-whisper`** | `faster-whisper` | `8000:8000` | CPU (AVX-512, int8) | Nhận diện tiếng Việt model `small` kèm bộ lọc VAD |
| **`piper-tts`** | `piper-tts` | `10200:10200` | CPU (ONNX Runtime) | Sinh giọng đọc `vi_VN-vais1000-medium` (22050Hz) |

### Sơ Đồ Luồng Dữ Liệu (Data Flow)

```
[ XiaoZhi ESP32 ] / [ mic_test.py ] / [ Client Apps ]
                      │
                      │ HTTP REST (Port 8080 - Bearer Key)
                      ▼
       ┌───────────────────────────────┐
       │   Unified Gateway (Port 8080) │
       └───┬──────────────┬────────────┘
           │              │
 ┌─────────┴────────┐     │ /v1/audio/*
 │ /v1/chat/*       │     ├──────────────────────────┐
 │ /api/agent       │     ▼                          ▼
 ▼                  │  ┌──────────────┐       ┌─────────────┐
┌─────────────────┐ │  │Faster-Whisper│       │  Piper-TTS  │
│   MCP Gateway   │ │  │ (Port 8000)  │       │(Port 10200) │
│   (Port 8008)   │ │  └──────────────┘       └─────────────┘
└────────┬────────┘ │         ▲                      ▲
         │ stdio    │         │ Audio In             │ Audio Out
         ▼          │         └──────────────────────┴──────── (XiaoZhi Hardware)
┌─────────────────┐ │
│   MCP Server    │ │
│ (FastMCP Tools) │ │
└─────────────────┘ │
         │ Turn 1 (with tools) & Turn 2 (with tool results)
         ▼
┌─────────────────┐
│  Ollama (GPU)   │
│  (Port 11434)   │
└─────────────────┘
```

---

## 3. Chi Tiết Phân Hệ MCP Agent Gateway (`services/`)

### A. MCP Server ([`services/mcp_server.py`](file:///services/mcp_server.py))
- Xây dựng bằng thư viện `mcp` (FastMCP), giao tiếp qua cơ chế `stdio` tiêu chuẩn (không tốn cổng mạng, độ trễ IPC cực thấp).
- Cung cấp 4 tools thiết thực với schema ngắn gọn, tối ưu cho khả năng hiểu của model 3B:
  1. `get_current_time()`: Lấy ngày, giờ, thứ trong tuần theo giờ Việt Nam chuẩn (GMT+7).
  2. `get_weather(city: str)`: Tra cứu thông tin thời tiết tại tỉnh/thành phố.
  3. `device_control(device_name: str, action: str)`: Điều khiển bật/tắt thiết bị smarthome.
  4. `get_dht20_environment()`: Đọc dữ liệu nhiệt độ và độ ẩm không khí thời gian thực từ cảm biến DHT20 trên nền tảng CoreIoT (`app.coreiot.io`).

### B. MCP Agent Gateway ([`services/mcp_gateway.py`](file:///services/mcp_gateway.py))
- Viết bằng FastAPI + `httpx`, hoạt động như một MCP Client:
  - Khi khởi động: Tự động kết nối tới `mcp_server.py` qua stdio, khám phá tools và chuyển đổi (convert) JSON Schema sang format `tools` chuẩn của OpenAI.
  - Xử lý **Turn 1**: Gửi prompt kèm định nghĩa tools tới Ollama `POST /v1/chat/completions`.
  - Phân tích phản hồi:
    - Nếu có `tool_calls`: Dispatch lệnh gọi hàm tới MCP Server, nhận kết quả và gửi tiếp **Turn 2** sang Ollama để tổng hợp câu trả lời tự nhiên ngắn gọn bằng tiếng Việt.
    - Nếu không có `tool_calls`: Trả thẳng kết quả suy luận trực tiếp.
  - Hỗ trợ cả phản hồi JSON thông thường và streaming SSE (`stream: true`) tương thích hoàn toàn với client phát âm thanh theo câu.
  - Đo latency chi tiết từng chặng và gán vào HTTP headers: `X-Latency-Inf1-Ms`, `X-Latency-Tool-Ms`, `X-Latency-Inf2-Ms`, `X-Latency-Total-Ms`.

---

## 4. Kết Quả Kiểm Thử Thực Tế & Đo Đạc Hiệu Năng (Benchmarks)

Hệ thống đã được kiểm thử trực tiếp trên phần cứng máy chủ cục bộ (NVIDIA RTX GPU + CPU đa luồng):

| Chỉ số kiểm thử | Kết quả đo đạc | Đánh giá |
| :--- | :--- | :--- |
| **Tốc độ sinh token của Ollama (`qwen2.5:3b-instruct`)** | **~67.13 tokens/giây** | Độc chiếm VRAM GPU, cực kỳ mượt mà |
| **Độ trễ thực thi MCP Tool qua stdio IPC** | **~4.4ms** | Gần như tức thì |
| **Tổng thời gian xử lý câu hỏi có Tool (Turn 1 + Tool + Turn 2)** | **~558ms - 640ms** | Hoàn thành trước khi timeout của thiết bị |
| **Độ trễ suy luận câu hỏi trực tiếp (Không Tool)** | **~760ms - 860ms** | Rất nhanh |
| **Độ trễ sinh giọng đọc Piper TTS** | **~0.69s** cho câu thoại 3.8s (RTF: **0.182x**) | Sinh âm thanh nhanh gấp 5.5 lần thời lượng nói thực tế |
| **Độ trễ nhận diện Faster-Whisper STT** | **~3.0s** (trên CPU với model `small` int8) | Nhận diện chính xác ngữ âm tiếng Việt |

---

## 5. Hướng Dẫn Vận Hành & Lệnh Kiểm Thử

### 1. Khởi động toàn bộ hệ thống
- **Cách 1-Click (Windows):** Chạy file [`start_all.bat`](file:///start_all.bat).
- **Cách lệnh Docker:**
  ```powershell
  docker compose up -d --build
  ```

### 2. Kiểm tra trạng thái các container
```powershell
docker ps
```
Cần đảm bảo 5 containers đều ở trạng thái `Up`: `gateway`, `mcp-gateway`, `ollama`, `faster-whisper`, `piper-tts`.

### 3. Chạy các bộ kịch bản kiểm thử
- **Kiểm thử phân luồng MCP (Direct LLM vs Tool Calling):**
  ```powershell
  python test_mcp_flow.py
  ```
- **Kiểm thử độc lập không cần Docker (Self-Test mode với Mock Ollama):**
  ```powershell
  python test_mcp_flow.py --self-test
  ```
- **Kiểm thử toàn trình 4 động cơ AI (LLM -> TTS -> STT -> Gateway):**
  ```powershell
  python test_pipeline.py
  ```
- **Bật trợ lý giọng nói Real-Time trực tiếp bằng micro laptop:**
  ```powershell
  python mic_test.py
  # hoặc nhấp đúp file: run_mic_test.bat
  ```

---

## 6. Hướng Dẫn Tích Hợp Thiết Bị XiaoZhi ESP32

### Thông số kết nối mạng
- **IP Máy chủ AI trong mạng LAN:** `10.127.27.65` *(Kiểm tra lại bằng `ipconfig` nếu đổi mạng)*
- **Cổng Gateway:** `8080`
- **Base URL:** `http://10.127.27.65:8080/v1`
- **API Key bảo mật:** `sk-xiaozhi-local-secret`

### Cấu hình mẫu cho XiaoZhi Server (`config.yaml`)
Dán cấu hình sau vào file `config.yaml` của máy chạy XiaoZhi Server (Máy B hoặc máy ảo):

```yaml
selected_module:
  ASR: OpenAIASR
  LLM: OpenAILLM
  TTS: OpenAITTS

ASR:
  OpenAIASR:
    type: openai
    base_url: http://10.127.27.65:8080/v1
    api_key: sk-xiaozhi-local-secret
    model_name: small
    language: vi
    output_dir: tmp/

LLM:
  OpenAILLM:
    type: openai
    base_url: http://10.127.27.65:8080/v1
    api_key: sk-xiaozhi-local-secret
    model_name: qwen2.5:3b-instruct
    temperature: 0.7

TTS:
  OpenAITTS:
    type: openai
    api_url: http://10.127.27.65:8080/v1/audio/speech
    api_key: sk-xiaozhi-local-secret
```

---

## 7. Hướng Dẫn Bổ Sung Thêm MCP Tools Mới

Để thêm chức năng mới cho XiaoZhi, chỉ cần khai báo thêm hàm trong [`services/mcp_server.py`](file:///services/mcp_server.py):

```python
@mcp.tool()
def search_knowledge_base(query: str) -> str:
    """Tra cứu thông tin tài liệu nội bộ."""
    # Logic tra cứu tại đây...
    return f"Kết quả tra cứu cho '{query}': ..."
```

Sau khi sửa:
```powershell
docker compose up -d --build mcp-gateway
```
`mcp-gateway` sẽ tự động khám phá tool mới, sinh JSON Schema và gửi sang Ollama mà không cần sửa code gateway!

---

## 8. Ghi Chú Kỹ Thuật & Khuyến Nghị Vận Hành

1. **Keep-Alive của Ollama**: Đã cấu hình `OLLAMA_KEEP_ALIVE=24h` để tránh việc GPU dọn giải phóng bộ nhớ giữa các lần đàm thoại, đảm bảo request đầu tiên không bị delay do nạp lại model.
2. **Khả năng của Model 3B**: Model `qwen2.5:3b-instruct` hoạt động tối ưu nhất khi số lượng tool từ 3-5 tools với mô tả tham số rõ ràng. Nếu bổ sung quá nhiều tool phức tạp, nên cân nhắc nâng lên `qwen2.5:7b-instruct` (nếu GPU có từ 8GB VRAM trở lên).
3. **Môi trường Python trên Host**: Nếu chạy script Python trực tiếp trên Windows ngoài Docker, hãy dùng `python -m pip install httpx mcp fastapi uvicorn` để đảm bảo cài đúng vào môi trường Python đang hoạt động.
4. **Tường lửa Windows (Firewall)**: Khi kết nối từ ESP32 qua Wi-Fi tới cổng 8080, đảm bảo Windows Defender Firewall đã cho phép kết nối Inbound trên Port 8080 (hoặc chọn Private Network).
