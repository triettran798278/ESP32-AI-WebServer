import os
import json
import time
from typing import Optional, Tuple, List
from .base import ASRProviderBase
from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType
import vosk

TAG = __name__
logger = setup_logging()

class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool = True):
        super().__init__()
        self.interface_type = InterfaceType.LOCAL
        self.model_path = config.get("model_path")
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file
        
        # Initialize VOSK model
        self.model = None
        self.recognizer = None
        self._load_model()
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    def _load_model(self):
        """加载VOSK模型"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"VOSK模型路径不存在: {self.model_path}")
                
            logger.bind(tag=TAG).info(f"正在加载VOSK模型: {self.model_path}")
            self.model = vosk.Model(self.model_path)

            # Initialize VOSK recognizer (sample rate must be 16kHz)
            self.recognizer = vosk.KaldiRecognizer(self.model, 16000)

            logger.bind(tag=TAG).info("VOSK模型加载成功")
        except Exception as e:
            logger.bind(tag=TAG).error(f"加载VOSK模型失败: {e}")
            raise

    async def speech_to_text(
        self, audio_data: List[bytes], session_id: str, audio_format: str = "opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本"""
        file_path = None
        try:
            # Check if model loaded successfully
            if not self.model:
                logger.bind(tag=TAG).error("VOSK模型未加载，无法进行识别")
                return "", None

            # Decode audio (if original format is Opus)
            if audio_format == "pcm":
                pcm_data = audio_data
            else:
                pcm_data = self.decode_opus(audio_data)
                
            if not pcm_data:
                logger.bind(tag=TAG).warning("解码后的PCM数据为空，无法进行识别")
                return "", None
                
            # Merge PCM data
            combined_pcm_data = b"".join(pcm_data)
            if len(combined_pcm_data) == 0:
                logger.bind(tag=TAG).warning("合并后的PCM数据为空")
                return "", None

            # Decide whether to save as WAV file
            if not self.delete_audio_file:
                file_path = self.save_audio_to_file(pcm_data, session_id)

            start_time = time.time()
            
            
            # Run recognition (VOSK recommends feeding 2000 bytes at a time)
            chunk_size = 2000
            text_result = ""
            
            for i in range(0, len(combined_pcm_data), chunk_size):
                chunk = combined_pcm_data[i:i+chunk_size]
                if self.recognizer.AcceptWaveform(chunk):
                    result = json.loads(self.recognizer.Result())
                    text = result.get('text', '')
                    if text:
                        text_result += text + " "
            
            # Get final result
            final_result = json.loads(self.recognizer.FinalResult())
            final_text = final_result.get('text', '')
            if final_text:
                text_result += final_text
            
            logger.bind(tag=TAG).debug(
                f"VOSK语音识别耗时: {time.time() - start_time:.3f}s | 结果: {text_result.strip()}"
            )
            
            return text_result.strip(), file_path
            
        except Exception as e:
            logger.bind(tag=TAG).error(f"VOSK语音识别失败: {e}")
            return "", None
        finally:
            # File cleanup logic
            if self.delete_audio_file and file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.bind(tag=TAG).debug(f"已删除临时音频文件: {file_path}")
                except Exception as e:
                    logger.bind(tag=TAG).error(f"文件删除失败: {file_path} | 错误: {e}")
