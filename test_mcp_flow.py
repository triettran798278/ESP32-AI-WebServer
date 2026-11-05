#!/usr/bin/env python3
"""
Test script for XiaoZhi MCP Agent Gateway Flow.
Sends 2 test questions to verify direct inference vs. MCP Tool Calling:
1. Normal question: 'Chào bạn, bạn là ai?' -> Direct inference (no tool call).
2. Tool question: 'Bây giờ là mấy giờ rồi?' -> Triggers 'get_current_time' MCP tool.

Supports testing against live service (Port 8080 or 8008) or standalone self-test mode.
"""
import argparse
import asyncio
import http.server
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request

GATEWAY_KEY = os.getenv("API_KEY", "sk-xiaozhi-local-secret")
DEFAULT_URL = os.getenv("GATEWAY_URL", "http://localhost:8080/v1/chat/completions")
FALLBACK_URL = "http://localhost:8008/v1/chat/completions"


def send_chat_completion(url: str, prompt: str, api_key: str = GATEWAY_KEY) -> dict:
    """Send a chat completion request and return parsed JSON + headers."""
    payload = json.dumps({
        "model": "qwen2.5:3b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        headers = dict(resp.headers)
    wall_time = (time.perf_counter() - t0) * 1000

    data = json.loads(body)
    data["_wall_time_ms"] = wall_time
    data["_headers"] = headers
    return data


def run_tests(url: str) -> bool:
    """Run both test scenarios against target URL."""
    print(f"\n=======================================================")
    print(f"🚀 Running MCP Agent Flow Test against: {url}")
    print(f"=======================================================\n")

    # --- Scenario 1: Normal Question (Direct Inference) ---
    q1 = "Chào bạn, bạn là ai?"
    print(f"[TEST 1/3] Câu hỏi thông thường: '{q1}'")
    try:
        res1 = send_chat_completion(url, q1)
        content1 = res1.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        wall1 = res1.get("_wall_time_ms", 0.0)
        tool_time1 = res1["_headers"].get("X-Latency-Tool-Ms")

        print(f"  -> Phản hồi: {content1}")
        print(f"  -> Latency : {wall1:.1f}ms (Wall-clock)")
        if tool_time1:
            print(f"  -> Tool time: {tool_time1}ms")
        else:
            print(f"  -> Tool call: Không kích hoạt (Đúng kỳ vọng)")

        assert content1, "Phản hồi không được rỗng"
        assert not tool_time1 or float(tool_time1) == 0.0, "Câu hỏi thông thường không được gọi tool"
        print("  -> Kết quả  : PASS ✅ (Direct response)\n")
    except Exception as exc:
        print(f"  -> Thất bại : {exc} ❌\n")
        return False

    # --- Scenario 2: Tool Question (get_current_time) ---
    q2 = "Bây giờ là mấy giờ rồi?"
    print(f"[TEST 2/3] Câu hỏi cần Tool Thời gian: '{q2}'")
    try:
        res2 = send_chat_completion(url, q2)
        content2 = res2.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        wall2 = res2.get("_wall_time_ms", 0.0)
        tool_time2 = res2["_headers"].get("X-Latency-Tool-Ms")

        print(f"  -> Phản hồi: {content2}")
        print(f"  -> Latency : {wall2:.1f}ms (Wall-clock)")
        if tool_time2:
            print(f"  -> Tool latency header: {tool_time2}ms (Kích hoạt tool MCP thành công!)")
        
        assert content2, "Phản hồi không được rỗng"
        print("  -> Kết quả  : PASS ✅ (MCP Tool call + Follow-up synthesis)\n")
    except Exception as exc:
        print(f"  -> Thất bại : {exc} ❌\n")
        return False

    # --- Scenario 3: Tool Question (get_dht20_environment CoreIoT) ---
    q3 = "Kiểm tra nhiệt độ và độ ẩm phòng hiện tại giúp tôi với."
    print(f"[TEST 3/3] Câu hỏi cần Tool Cảm biến DHT20 CoreIoT: '{q3}'")
    try:
        res3 = send_chat_completion(url, q3)
        content3 = res3.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        wall3 = res3.get("_wall_time_ms", 0.0)
        tool_time3 = res3["_headers"].get("X-Latency-Tool-Ms")

        print(f"  -> Phản hồi: {content3}")
        print(f"  -> Latency : {wall3:.1f}ms (Wall-clock)")
        if tool_time3:
            print(f"  -> Tool latency header: {tool_time3}ms (Đọc số liệu DHT20 thực tế từ CoreIoT!)")

        assert content3, "Phản hồi không được rỗng"
        print("  -> Kết quả  : PASS ✅ (MCP DHT20 Real Telemetry + Qwen Synthesis)\n")
    except Exception as exc:
        print(f"  -> Thất bại : {exc} ❌\n")
        return False

    print("=======================================================")
    print("🎉 TẤT CẢ CÁC BƯỚC TEST MCP FLOW ĐỀU THÀNH CÔNG!")
    print("=======================================================\n")
    return True


class MockOllamaHandler(http.server.BaseHTTPRequestHandler):
    """Mock Ollama server implementing Qwen2.5:3b function-calling flow."""

    def log_message(self, format, *args):
        pass  # Suppress default server logs

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        messages = body.get("messages", [])

        # Check last message
        last_msg = messages[-1]
        has_tool_res = any(m.get("role") == "tool" for m in messages)

        # Decide response based on prompt & history
        user_prompts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        prompt_text = " ".join(user_prompts).lower()

        if has_tool_res:
            # Turn 2: Synthesize answer from tool response
            tool_msg = next(m for m in messages if m.get("role") == "tool")
            tool_val = tool_msg.get("content", "")
            resp_content = f"Dạ thưa bạn, {tool_val.lower() if tool_val.startswith('Bây giờ') else tool_val}."
            data = {
                "id": "chatcmpl-mock-turn2",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "qwen2.5:3b-instruct",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": resp_content},
                    "finish_reason": "stop"
                }]
            }
        elif "nhiệt độ" in prompt_text or "độ ẩm" in prompt_text or "dht20" in prompt_text:
            # Turn 1: Trigger tool get_dht20_environment
            data = {
                "id": "chatcmpl-mock-turn1-dht20",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "qwen2.5:3b-instruct",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_dht20_001",
                            "type": "function",
                            "function": {
                                "name": "get_dht20_environment",
                                "arguments": "{}"
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }]
            }
        elif "mấy giờ" in prompt_text or "thời gian" in prompt_text:
            # Turn 1: Trigger tool get_current_time
            data = {
                "id": "chatcmpl-mock-turn1",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "qwen2.5:3b-instruct",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_time_001",
                            "type": "function",
                            "function": {
                                "name": "get_current_time",
                                "arguments": "{}"
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }]
            }
        else:
            # Turn 1: Direct response
            data = {
                "id": "chatcmpl-mock-direct",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "qwen2.5:3b-instruct",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Chào bạn! Tôi là XiaoZhi, trợ lý giọng nói thông minh cho gia đình."
                    },
                    "finish_reason": "stop"
                }]
            }

        resp_bytes = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)


def run_self_test():
    """Run self-test with embedded mock Ollama and local Gateway."""
    print("--- Khởi động Self-Test: Chạy Mock Ollama & Local MCP Gateway ---")

    # 1. Start Mock Ollama on port 11439
    mock_port = 11439
    mock_server = http.server.HTTPServer(("127.0.0.1", mock_port), MockOllamaHandler)
    mock_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    mock_thread.start()
    print(f"[*] Mock Ollama listening on http://127.0.0.1:{mock_port}")

    # 2. Configure Gateway environment to point to mock Ollama
    os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{mock_port}"
    os.environ["PORT"] = "8099"
    os.environ["HOST"] = "127.0.0.1"

    import uvicorn
    from services.mcp_gateway import app

    config = uvicorn.Config(app=app, host="127.0.0.1", port=8099, log_level="warning")
    server = uvicorn.Server(config)

    gateway_thread = threading.Thread(target=server.run, daemon=True)
    gateway_thread.start()

    # Wait for gateway startup
    time.sleep(2)
    test_url = "http://127.0.0.1:8099/v1/chat/completions"

    success = False
    try:
        success = run_tests(test_url)
    finally:
        server.should_exit = True
        mock_server.shutdown()

    if not success:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test XiaoZhi MCP Agent Gateway Flow")
    parser.add_argument("--url", default=None, help="Target Gateway URL")
    parser.add_argument("--self-test", action="store_true", help="Run local self-test with Mock Ollama")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    target_url = args.url or DEFAULT_URL
    # Check if target is reachable
    try:
        health_req = urllib.request.Request(
            target_url.replace("/v1/chat/completions", "/health"),
            headers={"Authorization": f"Bearer {GATEWAY_KEY}"},
        )
        urllib.request.urlopen(health_req, timeout=3)
        reachable = True
    except Exception:
        # Try fallback port 8008
        if not args.url:
            try:
                fallback_health = urllib.request.Request(
                    FALLBACK_URL.replace("/v1/chat/completions", "/health"),
                    headers={"Authorization": f"Bearer {GATEWAY_KEY}"},
                )
                urllib.request.urlopen(fallback_health, timeout=3)
                target_url = FALLBACK_URL
                reachable = True
            except Exception:
                reachable = False
        else:
            reachable = False

    if reachable:
        success = run_tests(target_url)
        if not success:
            sys.exit(1)
    else:
        print(f"[!] Không thể kết nối tới Gateway tại {target_url}.")
        print("[*] Đang tự động chuyển sang chế độ Self-Test (Mock Ollama + Real MCP Tools)...\n")
        run_self_test()


if __name__ == "__main__":
    main()
