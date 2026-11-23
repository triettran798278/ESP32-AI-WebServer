import os
import tempfile
from typing import Optional, Tuple, List
import dashscope
from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

tag = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        # Audio file upload type, streaming text recognition output
        self.interface_type = InterfaceType.NON_STREAM
        """Qwen3-ASR-Flash ASR初始化"""
        
        # Configuration parameters
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("Qwen3-ASR-Flash 需要配置 api_key")
            
        self.model_name = config.get("model_name", "qwen3-asr-flash")
        self.output_dir = config.get("output_dir", "./audio_output")
        self.delete_audio_file = delete_audio_file
        
        # ASR options
        self.enable_lid = config.get("enable_lid", True)  # Automatic language identification
        self.enable_itn = config.get("enable_itn", True)  # Inverse text normalization
        self.language = config.get("language", None)  # Specified language, auto-detect by default
        self.context = config.get("context", "")  # Context info to improve recognition accuracy
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    def _prepare_audio_file(self, pcm_data: bytes) -> str:
        """将PCM数据转换为WAV文件并返回文件路径"""
        try:
            import wave
            
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                
            # Write WAV format
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)      # Mono
                wav_file.setsampwidth(2)      # 16-bit
                wav_file.setframerate(16000)  # 16kHz sample rate
                wav_file.writeframes(pcm_data)
                
            return temp_path
            
        except Exception as e:
            logger.bind(tag=tag).error(f"音频文件准备失败: {e}")
            return None

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本"""
        temp_file_path = None
        file_path = None
        
        try:
            # Decode audio data
            if audio_format == "pcm":
                pcm_data = opus_data
            else:
                pcm_data = self.decode_opus(opus_data)
            
            combined_pcm_data = b"".join(pcm_data)
            if len(combined_pcm_data) == 0:
                logger.bind(tag=tag).warning("音频数据为空")
                return "", None
            
            # Prepare audio file
            temp_file_path = self._prepare_audio_file(combined_pcm_data)
            if not temp_file_path:
                return "", None
            
            # Save audio file (if needed)
            if not self.delete_audio_file:
                file_path = self.save_audio_to_file(pcm_data, session_id)
            
            # Build request messages
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"audio": temp_file_path}
                    ]
                }
            ]
            
            # Add system message if context is provided
            if self.context:
                messages.insert(0, {
                    "role": "system", 
                    "content": [
                        {"text": self.context}
                    ]
                })
            
            # Prepare ASR options
            asr_options = {
                "enable_lid": self.enable_lid,
                "enable_itn": self.enable_itn
            }
            
            # Add language to options if specified
            if self.language:
                asr_options["language"] = self.language
            
            # Set API key
            dashscope.api_key = self.api_key
            
            # Send streaming request
            response = dashscope.MultiModalConversation.call(
                model=self.model_name,
                messages=messages,
                result_format="message",
                asr_options=asr_options,
                stream=True
            )
            
            # Handle streaming response
            full_text = ""
            for chunk in response:
                try:
                    text = chunk["output"]["choices"][0]["message"].content[0]["text"]
                    # Update to latest full text
                    full_text = text.strip()
                except:
                    pass
            
            return full_text, file_path
                
        except Exception as e:
            logger.bind(tag=tag).error(f"语音识别失败: {e}")
            return "", file_path
            
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.bind(tag=tag).warning(f"清理临时文件失败: {e}")