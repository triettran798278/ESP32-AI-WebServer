import asyncio
import json
from typing import Dict, Any

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.providers.tools.device_mcp import handle_mcp_message

TAG = __name__

class ServerTextMessageHandler(TextMessageHandler):
    """MCP消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.SERVER

    async def handle(self, conn, msg_json: Dict[str, Any]) -> None:
        # Verify secret if config is loaded from API
        if not conn.read_config_from_api:
            return
        # Get secret from POST request
        post_secret = msg_json.get("content", {}).get("secret", "")
        secret = conn.config["manager-api"].get("secret", "")
        # Return error if secret does not match
        if post_secret != secret:
            await conn.websocket.send(
                json.dumps(
                    {
                        "type": "server",
                        "status": "error",
                        "message": "服务器密钥验证失败",
                    }
                )
            )
            return
        # Dynamically update config
        if msg_json["action"] == "update_config":
            try:
                # Update WebSocketServer config
                if not conn.server:
                    await conn.websocket.send(
                        json.dumps(
                            {
                                "type": "server",
                                "status": "error",
                                "message": "无法获取服务器实例",
                                "content": {"action": "update_config"},
                            }
                        )
                    )
                    return

                if not await conn.server.update_config():
                    await conn.websocket.send(
                        json.dumps(
                            {
                                "type": "server",
                                "status": "error",
                                "message": "更新服务器配置失败",
                                "content": {"action": "update_config"},
                            }
                        )
                    )
                    return

                # Send success response
                await conn.websocket.send(
                    json.dumps(
                        {
                            "type": "server",
                            "status": "success",
                            "message": "配置更新成功",
                            "content": {"action": "update_config"},
                        }
                    )
                )
            except Exception as e:
                conn.logger.bind(tag=TAG).error(f"更新配置失败: {str(e)}")
                await conn.websocket.send(
                    json.dumps(
                        {
                            "type": "server",
                            "status": "error",
                            "message": f"更新配置失败: {str(e)}",
                            "content": {"action": "update_config"},
                        }
                    )
                )
        # Restart server
        elif msg_json["action"] == "restart":
            await conn.handle_restart(msg_json)