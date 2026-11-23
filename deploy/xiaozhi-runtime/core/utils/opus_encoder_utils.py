"""
Opus编码工具类
将PCM音频数据编码为Opus格式
"""

import logging
import traceback
import numpy as np
from opuslib_next import Encoder
from opuslib_next import constants
from typing import Optional, Callable, Any

class OpusEncoderUtils:
    """PCM到Opus的编码器"""

    def __init__(self, sample_rate: int, channels: int, frame_size_ms: int):
        """
        初始化Opus编码器

        Args:
            sample_rate: 采样率 (Hz)
            channels: 通道数 (1=单声道, 2=立体声)
            frame_size_ms: 帧大小 (毫秒)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size_ms = frame_size_ms
        # Samples per frame = sample_rate * frame_size_ms / 1000
        self.frame_size = (sample_rate * frame_size_ms) // 1000
        # Total frame size = samples per frame * channels
        self.total_frame_size = self.frame_size * channels

        # Bitrate and complexity settings
        self.bitrate = 24000  # bps
        self.complexity = 10  # Highest quality

        # Initialize empty buffer
        self.buffer = np.array([], dtype=np.int16)

        try:
            # Create Opus encoder
            self.encoder = Encoder(
                sample_rate, channels, constants.APPLICATION_AUDIO  # Audio optimization mode
            )
            self.encoder.bitrate = self.bitrate
            self.encoder.complexity = self.complexity
            self.encoder.signal = constants.SIGNAL_VOICE  # Voice signal optimization
        except Exception as e:
            logging.error(f"初始化Opus编码器失败: {e}")
            raise RuntimeError("初始化失败") from e

    def reset_state(self):
        """重置编码器状态"""
        self.encoder.reset_state()
        self.buffer = np.array([], dtype=np.int16)

    def encode_pcm_to_opus_stream(self, pcm_data: bytes, end_of_stream: bool, callback: Callable[[Any], Any]):
        """
        将PCM数据编码为Opus格式，以流式方式进行处理

        Args:
            pcm_data: PCM字节数据
            end_of_stream: 是否为流的结束,
            callback: opus处理方法

        Returns:
            Opus数据包列表
        """
        # Convert bytes to int16 array
        new_samples = self._convert_bytes_to_shorts(pcm_data)

        # Validate PCM data
        self._validate_pcm_data(new_samples)

        # Append new data to buffer
        self.buffer = np.append(self.buffer, new_samples)

        offset = 0

        # Process all complete frames
        while offset <= len(self.buffer) - self.total_frame_size:
            frame = self.buffer[offset : offset + self.total_frame_size]
            output = self._encode(frame)
            if output:
                callback(output)
            offset += self.total_frame_size

        # Keep remaining unprocessed samples
        self.buffer = self.buffer[offset:]

        # Process remaining data at end of stream
        if end_of_stream and len(self.buffer) > 0:
            # Create last frame padded with zeros
            last_frame = np.zeros(self.total_frame_size, dtype=np.int16)
            last_frame[: len(self.buffer)] = self.buffer

            output = self._encode(last_frame)
            if output:
                callback(output)
            self.buffer = np.array([], dtype=np.int16)

    def _encode(self, frame: np.ndarray) -> Optional[bytes]:
        """编码一帧音频数据"""
        try:
            # Encoder already released; skip encoding
            if not hasattr(self, 'encoder') or self.encoder is None:
                return None
            # Convert numpy array to bytes
            frame_bytes = frame.tobytes()
            # opuslib requires input byte count to be a multiple of channels * 2
            encoded = self.encoder.encode(frame_bytes, self.frame_size)
            return encoded
        except Exception as e:
            logging.error(f"Opus编码失败: {e}")
            traceback.print_exc()
            return None

    def _convert_bytes_to_shorts(self, bytes_data: bytes) -> np.ndarray:
        """将字节数组转换为short数组 (16位PCM)"""
        # Assume little-endian 16-bit PCM input
        return np.frombuffer(bytes_data, dtype=np.int16)

    def _validate_pcm_data(self, pcm_shorts: np.ndarray) -> None:
        """验证PCM数据是否有效"""
        # 16-bit PCM range is -32768 to 32767
        if np.any((pcm_shorts < -32768) | (pcm_shorts > 32767)):
            invalid_samples = pcm_shorts[(pcm_shorts < -32768) | (pcm_shorts > 32767)]
            logging.warning(f"发现无效PCM样本: {invalid_samples[:5]}...")
            # In practice, can clip instead of raising an exception
            # np.clip(pcm_shorts, -32768, 32767, out=pcm_shorts)

    def close(self):
        """关闭编码器并释放资源"""
        if hasattr(self, 'encoder') and self.encoder:
            try:
                del self.encoder
                self.encoder = None
            except Exception as e:
                logging.error(f"Error releasing Opus encoder: {e}")