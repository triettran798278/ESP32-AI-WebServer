import time
import asyncio
from collections import deque
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class AudioRateController:
    """
    音频速率控制器 - 按照60ms帧时长精确控制音频发送
    解决高并发下的时间累积误差问题
    """

    def __init__(self, frame_duration=60):
        """
        Args:
            frame_duration: 单个音频帧时长（毫秒），默认60ms
        """
        self.frame_duration = frame_duration
        self.queue = deque()
        self.play_position = 0  # Virtual playback position (ms)
        self.start_timestamp = None  # Start timestamp (read-only, never modified)
        self.pending_send_task = None
        self.logger = logger
        self.queue_empty_event = asyncio.Event()  # Queue empty event
        self.queue_empty_event.set()  # Initially empty
        self.queue_has_data_event = asyncio.Event()  # Queue has-data event

    def reset(self):
        """重置控制器状态"""
        if self.pending_send_task and not self.pending_send_task.done():
            self.pending_send_task.cancel()
            # Cancelled task will clean up on next event loop tick; no need to block

        self.queue.clear()
        self.play_position = 0
        self.start_timestamp = None  # Set by the first audio packet
        # Update queue events
        self.queue_empty_event.set()
        self.queue_has_data_event.clear()

    def add_audio(self, opus_packet):
        """添加音频包到队列"""
        self.queue.append(("audio", opus_packet))
        # Update queue events
        self.queue_empty_event.clear()
        self.queue_has_data_event.set()

    def add_message(self, message_callback):
        """
        添加消息到队列（立即发送，不占用播放时间）

        Args:
            message_callback: 消息发送回调函数 async def()
        """
        self.queue.append(("message", message_callback))
        # Update queue events
        self.queue_empty_event.clear()
        self.queue_has_data_event.set()

    def _get_elapsed_ms(self):
        """获取已经过的时间（毫秒）"""
        if self.start_timestamp is None:
            return 0
        return (time.monotonic() - self.start_timestamp) * 1000

    async def check_queue(self, send_audio_callback):
        """
        检查队列并按时发送音频/消息

        Args:
            send_audio_callback: 发送音频的回调函数 async def(opus_packet)
        """
        while self.queue:
            item = self.queue[0]
            item_type = item[0]

            if item_type == "message":
                # Message type: send immediately without consuming playback time
                _, message_callback = item
                self.queue.popleft()
                try:
                    await message_callback()
                except Exception as e:
                    self.logger.bind(tag=TAG).error(f"发送消息失败: {e}")
                    raise

            elif item_type == "audio":
                if self.start_timestamp is None:
                    self.start_timestamp = time.monotonic()

                _, opus_packet = item

                # Loop until scheduled send time is reached
                while True:
                    # Compute time difference
                    elapsed_ms = self._get_elapsed_ms()
                    output_ms = self.play_position

                    if elapsed_ms < output_ms:
                        # Not yet time to send; compute wait duration
                        wait_ms = output_ms - elapsed_ms

                        # Sleep and re-check (interruptible)
                        try:
                            await asyncio.sleep(wait_ms / 1000)
                        except asyncio.CancelledError:
                            self.logger.bind(tag=TAG).debug("音频发送任务被取消")
                            raise
                        # Re-check elapsed time after sleeping (loop back to while True)
                    else:
                        # Time reached; exit wait loop
                        break

                # Time reached; pop from queue and send
                self.queue.popleft()
                self.play_position += self.frame_duration
                try:
                    await send_audio_callback(opus_packet)
                except Exception as e:
                    self.logger.bind(tag=TAG).error(f"发送音频失败: {e}")
                    raise

        # Clear data event after queue is drained
        self.queue_empty_event.set()
        self.queue_has_data_event.clear()

    def start_sending(self, send_audio_callback):
        """
        启动异步发送任务

        Args:
            send_audio_callback: 发送音频的回调函数

        Returns:
            asyncio.Task: 发送任务
        """

        async def _send_loop():
            try:
                while True:
                    # Wait for queue data event instead of busy-polling CPU
                    await self.queue_has_data_event.wait()

                    await self.check_queue(send_audio_callback)
            except asyncio.CancelledError:
                self.logger.bind(tag=TAG).debug("音频发送循环已停止")
            except Exception as e:
                self.logger.bind(tag=TAG).error(f"音频发送循环异常: {e}")

        self.pending_send_task = asyncio.create_task(_send_loop())
        return self.pending_send_task

    def stop_sending(self):
        """停止发送任务"""
        if self.pending_send_task and not self.pending_send_task.done():
            self.pending_send_task.cancel()
            self.logger.bind(tag=TAG).debug("已取消音频发送任务")
