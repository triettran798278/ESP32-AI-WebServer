# Cấu hình Kết nối XiaoZhi Server (Full-Local AI Backend)

Tài liệu này cung cấp thông số kết nối và mẫu cấu hình chuẩn (`YAML` và `JSON`) để kết nối **XiaoZhi ESP32 Server** tới cụm AI chạy cục bộ.

---

## 1. Kiến trúc Cổng Hợp Nhất (Unified AI Gateway)

Hệ thống đã được trang bị **AI Gateway** tập trung trên **Cổng 8080** với **1 API Key duy nhất**:
- **Gateway Endpoint:** `http://<IP_MÁY_A>:8080/v1`
- **API Key bảo mật:** `sk-xiaozhi-local-secret` *(hoặc tự đổi trong `docker-compose.yml`)*

Gateway tự động nhận diện và phân luồng thông minh:
- `/v1/chat/completions` $\rightarrow$ Chuyển tiếp tới **Ollama LLM (GPU)**
- `/v1/audio/transcriptions` $\rightarrow$ Chuyển tiếp tới **Faster-Whisper STT (CPU)**
- `/v1/audio/speech` $\rightarrow$ Chuyển tiếp tới **Piper TTS (CPU)**

---

## 2. Cấu hình mẫu `config.yaml` cho Máy B (XiaoZhi Server)

Cực kỳ gọn gàng vì tất cả các module đều dùng chung 1 Base URL và 1 API Key:

```yaml
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
```
*(Thay thế `192.168.1.150` bằng IP thực tế của Máy A)*.

---

## 3. Cấu hình JSON tổng quát

```json
{
  "api_key": "sk-xiaozhi-local-secret",
  "base_url": "http://192.168.1.150:8080/v1",
  "llm": {
    "provider": "openai_compatible",
    "model": "qwen2.5:3b-instruct"
  },
  "stt": {
    "provider": "openai_whisper",
    "model": "small",
    "language": "vi"
  },
  "tts": {
    "provider": "openai_tts",
    "model": "tts-1",
    "voice": "vi_VN-vais1000-medium"
  }
}
```
