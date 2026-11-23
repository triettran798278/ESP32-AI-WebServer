import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
import os
from typing import Optional, Tuple, List
from core.providers.asr.dto.dto import InterfaceType
import requests
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    API_URL = "https://asr.tencentcloudapi.com"
    API_VERSION = "2019-06-14"
    FORMAT = "pcm"  # Supported audio formats: pcm, wav, mp3

    def __init__(self, config: dict, delete_audio_file: bool = True):
        super().__init__()
        self.interface_type = InterfaceType.NON_STREAM
        self.secret_id = config.get("secret_id")
        self.secret_key = config.get("secret_key")
        self.output_dir = config.get("output_dir")
        self.delete_audio_file = delete_audio_file

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本"""
        if not opus_data:
            logger.bind(tag=TAG).warning("音频数据为空！")
            return None, None

        file_path = None
        try:
            # Check if configuration is set
            if not self.secret_id or not self.secret_key:
                logger.bind(tag=TAG).error("腾讯云语音识别配置未设置，无法进行识别")
                return None, file_path

            # Decode Opus audio data to PCM
            if audio_format == "pcm":
                pcm_data = opus_data
            else:
                pcm_data = self.decode_opus(opus_data)
            combined_pcm_data = b"".join(pcm_data)

            # Decide whether to save as WAV file
            if self.delete_audio_file:
                pass
            else:
                self.save_audio_to_file(pcm_data, session_id)

            # Convert audio data to Base64
            base64_audio = base64.b64encode(combined_pcm_data).decode("utf-8")

            # Build request body
            request_body = self._build_request_body(base64_audio)

            # Get authorization headers
            timestamp, authorization = self._get_auth_headers(request_body)

            # Send request
            start_time = time.time()
            result = self._send_request(request_body, timestamp, authorization)

            if result:
                logger.bind(tag=TAG).debug(
                    f"腾讯云语音识别耗时: {time.time() - start_time:.3f}s | 结果: {result}"
                )

            return result, file_path

        except Exception as e:
            logger.bind(tag=TAG).error(f"处理音频时发生错误！{e}", exc_info=True)
            return None, file_path

    def _build_request_body(self, base64_audio: str) -> str:
        """构建请求体"""
        request_map = {
            "ProjectId": 0,
            "SubServiceType": 2,  # Short sentence recognition
            "EngSerViceType": "16k_zh",  # General Mandarin Chinese
            "SourceType": 1,  # Audio data from voice file
            "VoiceFormat": self.FORMAT,  # Audio format
            "Data": base64_audio,  # Base64-encoded audio data
            "DataLen": len(base64_audio),  # Data length
        }
        return json.dumps(request_map)

    def _get_auth_headers(self, request_body: str) -> Tuple[str, str]:
        """获取认证头"""
        try:
            # Get current UTC timestamp
            now = datetime.now(timezone.utc)
            timestamp = str(int(now.timestamp()))
            date = now.strftime("%Y-%m-%d")

            # Service name must be "asr"
            service = "asr"

            # Build credential scope
            credential_scope = f"{date}/{service}/tc3_request"

            # Use TC3-HMAC-SHA256 signing method
            algorithm = "TC3-HMAC-SHA256"

            # Build canonical request string
            http_request_method = "POST"
            canonical_uri = "/"
            canonical_query_string = ""

            # Note: headers must be sorted in ascending ASCII order with lowercase keys and values
            # Must include content-type and host headers
            content_type = "application/json; charset=utf-8"
            host = "asr.tencentcloudapi.com"
            action = "SentenceRecognition"  # Action name

            # Build canonical headers, preserving order and format
            canonical_headers = (
                f"content-type:{content_type.lower()}\n"
                + f"host:{host.lower()}\n"
                + f"x-tc-action:{action.lower()}\n"
            )

            signed_headers = "content-type;host;x-tc-action"

            # Request payload hash
            payload_hash = self._sha256_hex(request_body)

            # Build canonical request string
            canonical_request = (
                f"{http_request_method}\n"
                + f"{canonical_uri}\n"
                + f"{canonical_query_string}\n"
                + f"{canonical_headers}\n"
                + f"{signed_headers}\n"
                + f"{payload_hash}"
            )

            # Hash the canonical request
            hashed_canonical_request = self._sha256_hex(canonical_request)

            # Build string to sign
            string_to_sign = (
                f"{algorithm}\n"
                + f"{timestamp}\n"
                + f"{credential_scope}\n"
                + f"{hashed_canonical_request}"
            )

            # Derive signing key
            secret_date = self._hmac_sha256(f"TC3{self.secret_key}", date)
            secret_service = self._hmac_sha256(secret_date, service)
            secret_signing = self._hmac_sha256(secret_service, "tc3_request")

            # Compute signature
            signature = self._bytes_to_hex(
                self._hmac_sha256(secret_signing, string_to_sign)
            )

            # Build Authorization header
            authorization = (
                f"{algorithm} "
                + f"Credential={self.secret_id}/{credential_scope}, "
                + f"SignedHeaders={signed_headers}, "
                + f"Signature={signature}"
            )

            return timestamp, authorization

        except Exception as e:
            logger.bind(tag=TAG).error(f"生成认证头失败: {e}", exc_info=True)
            raise RuntimeError(f"生成认证头失败: {e}")

    def _send_request(
        self, request_body: str, timestamp: str, authorization: str
    ) -> Optional[str]:
        """发送请求到腾讯云API"""
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Host": "asr.tencentcloudapi.com",
            "Authorization": authorization,
            "X-TC-Action": "SentenceRecognition",
            "X-TC-Version": self.API_VERSION,
            "X-TC-Timestamp": timestamp,
            "X-TC-Region": "ap-shanghai",
        }

        try:
            response = requests.post(self.API_URL, headers=headers, data=request_body)

            if not response.ok:
                raise IOError(f"请求失败: {response.status_code} {response.reason}")

            response_json = response.json()

            # Check for errors
            if "Response" in response_json and "Error" in response_json["Response"]:
                error = response_json["Response"]["Error"]
                error_code = error["Code"]
                error_message = error["Message"]
                raise IOError(f"API返回错误: {error_code}: {error_message}")

            # Extract recognition result
            if "Response" in response_json and "Result" in response_json["Response"]:
                return response_json["Response"]["Result"]
            else:
                logger.bind(tag=TAG).warning(f"响应中没有识别结果: {response_json}")
                return ""

        except Exception as e:
            logger.bind(tag=TAG).error(f"发送请求失败: {e}", exc_info=True)
            return None

    def _sha256_hex(self, data: str) -> str:
        """计算字符串的SHA256哈希值"""
        digest = hashlib.sha256(data.encode("utf-8")).digest()
        return self._bytes_to_hex(digest)

    def _hmac_sha256(self, key, data: str) -> bytes:
        """计算HMAC-SHA256"""
        if isinstance(key, str):
            key = key.encode("utf-8")

        return hmac.new(key, data.encode("utf-8"), hashlib.sha256).digest()

    def _bytes_to_hex(self, bytes_data: bytes) -> str:
        """字节数组转十六进制字符串"""
        return "".join(f"{b:02x}" for b in bytes_data)
