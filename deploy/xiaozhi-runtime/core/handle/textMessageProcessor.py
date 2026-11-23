import json

from core.handle.textMessageHandlerRegistry import TextMessageHandlerRegistry

TAG = __name__


class TextMessageProcessor:
    """消息处理器主类"""

    def __init__(self, registry: TextMessageHandlerRegistry):
        self.registry = registry

    async def process_message(self, conn, message: str) -> None:
        """处理消息的主入口"""
        try:
            # Parse JSON message
            msg_json = json.loads(message)

            # Handle JSON message
            if isinstance(msg_json, dict):
                message_type = msg_json.get("type")

                # Log message
                conn.logger.bind(tag=TAG).info(f"收到{message_type}消息：{message}")

                # Get and execute handler
                handler = self.registry.get_handler(message_type)
                if handler:
                    await handler.handle(conn, msg_json)
                else:
                    conn.logger.bind(tag=TAG).error(f"收到未知类型消息：{message}")
            # Handle numeric-only message
            elif isinstance(msg_json, int):
                conn.logger.bind(tag=TAG).info(f"收到数字消息：{message}")
                await conn.websocket.send(message)

        except json.JSONDecodeError:
            # Forward non-JSON message directly
            conn.logger.bind(tag=TAG).error(f"解析到错误的消息：{message}")
            await conn.websocket.send(message)
