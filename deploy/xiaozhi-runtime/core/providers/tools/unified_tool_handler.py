"""统一工具处理器"""

import json
from typing import Dict, List, Any, Optional
from config.logger import setup_logging
from plugins_func.loadplugins import auto_import_modules

from .base import ToolType
from plugins_func.register import Action, ActionResponse
from .unified_tool_manager import ToolManager
from .server_plugins import ServerPluginExecutor
from .server_mcp import ServerMCPExecutor
from .device_iot import DeviceIoTExecutor
from .device_mcp import DeviceMCPExecutor
from .mcp_endpoint import MCPEndpointExecutor


class UnifiedToolHandler:
    """统一工具处理器"""

    def __init__(self, conn):
        self.conn = conn
        self.config = conn.config
        self.logger = setup_logging()

        # Create tool manager
        self.tool_manager = ToolManager(conn)

        # Create executors
        self.server_plugin_executor = ServerPluginExecutor(conn)
        self.server_mcp_executor = ServerMCPExecutor(conn)
        self.device_iot_executor = DeviceIoTExecutor(conn)
        self.device_mcp_executor = DeviceMCPExecutor(conn)
        self.mcp_endpoint_executor = MCPEndpointExecutor(conn)

        # Register executors
        self.tool_manager.register_executor(
            ToolType.SERVER_PLUGIN, self.server_plugin_executor
        )
        self.tool_manager.register_executor(
            ToolType.SERVER_MCP, self.server_mcp_executor
        )
        self.tool_manager.register_executor(
            ToolType.DEVICE_IOT, self.device_iot_executor
        )
        self.tool_manager.register_executor(
            ToolType.DEVICE_MCP, self.device_mcp_executor
        )
        self.tool_manager.register_executor(
            ToolType.MCP_ENDPOINT, self.mcp_endpoint_executor
        )

        # Initialization flag
        self.finish_init = False

    async def _initialize(self):
        """异步初始化"""
        try:
            # Auto-import plugin modules
            auto_import_modules("plugins_func.functions")

            # Initialize server MCP
            await self.server_mcp_executor.initialize()

            # Initialize MCP endpoint
            await self._initialize_mcp_endpoint()

            # Initialize Home Assistant if needed
            self._initialize_home_assistant()

            self.finish_init = True
            self.logger.debug("统一工具处理器初始化完成")

            # Log currently supported tools
            self.current_support_functions()

        except Exception as e:
            self.logger.error(f"统一工具处理器初始化失败: {e}")

    async def _initialize_mcp_endpoint(self):
        """初始化MCP接入点"""
        try:
            from .mcp_endpoint import connect_mcp_endpoint

            # Get MCP endpoint URL from config
            mcp_endpoint_url = self.config.get("mcp_endpoint", "")

            if (
                mcp_endpoint_url
                and "你的" not in mcp_endpoint_url
                and mcp_endpoint_url != "null"
            ):
                self.logger.info(f"正在初始化MCP接入点: {mcp_endpoint_url}")
                mcp_endpoint_client = await connect_mcp_endpoint(
                    mcp_endpoint_url, self.conn
                )

                if mcp_endpoint_client:
                    # Save MCP endpoint client to connection object
                    self.conn.mcp_endpoint_client = mcp_endpoint_client
                    self.logger.info("MCP接入点初始化成功")
                else:
                    self.logger.warning("MCP接入点初始化失败")

        except Exception as e:
            self.logger.error(f"初始化MCP接入点失败: {e}")

    def _initialize_home_assistant(self):
        """初始化Home Assistant提示词"""
        try:
            from plugins_func.functions.hass_init import append_devices_to_prompt

            append_devices_to_prompt(self.conn)
        except ImportError:
            pass  # Ignore import error
        except Exception as e:
            self.logger.error(f"初始化Home Assistant失败: {e}")

    def get_functions(self) -> List[Dict[str, Any]]:
        """获取所有工具的函数描述"""
        return self.tool_manager.get_function_descriptions()

    def current_support_functions(self) -> List[str]:
        """获取当前支持的函数名称列表"""
        func_names = self.tool_manager.get_supported_tool_names()
        self.logger.info(f"当前支持的函数列表: {func_names}")
        return func_names

    def upload_functions_desc(self):
        """刷新函数描述列表"""
        self.tool_manager.refresh_tools()
        self.logger.info("函数描述列表已刷新")

    def has_tool(self, tool_name: str) -> bool:
        """检查是否有指定工具"""
        return self.tool_manager.has_tool(tool_name)

    async def handle_llm_function_call(
        self, conn, function_call_data: Dict[str, Any]
    ) -> Optional[ActionResponse]:
        """处理LLM函数调用"""
        try:
            # Handle multiple function calls
            if "function_calls" in function_call_data:
                responses = []
                for call in function_call_data["function_calls"]:
                    result = await self.tool_manager.execute_tool(
                        call["name"], call.get("arguments", {})
                    )
                    responses.append(result)
                return self._combine_responses(responses)

            # Handle single function call
            function_name = function_call_data["name"]
            arguments = function_call_data.get("arguments", {})

            # If arguments is a string, try parsing as JSON
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    self.logger.error(f"无法解析函数参数: {arguments}")
                    return ActionResponse(
                        action=Action.ERROR,
                        response="无法解析函数参数",
                    )

            self.logger.debug(f"调用函数: {function_name}, 参数: {arguments}")

            # Execute tool call
            result = await self.tool_manager.execute_tool(function_name, arguments)
            return result

        except Exception as e:
            self.logger.error(f"处理function call错误: {e}")
            return ActionResponse(action=Action.ERROR, response=str(e))

    def _combine_responses(self, responses: List[ActionResponse]) -> ActionResponse:
        """合并多个函数调用的响应"""
        if not responses:
            return ActionResponse(action=Action.NONE, response="无响应")

        # If any error occurred, return the first error
        for response in responses:
            if response.action == Action.ERROR:
                return response

        # Merge all successful responses
        contents = []
        responses_text = []

        for response in responses:
            if response.content:
                contents.append(response.content)
            if response.response:
                responses_text.append(response.response)

        # Determine final action type
        final_action = Action.RESPONSE
        for response in responses:
            if response.action == Action.REQLLM:
                final_action = Action.REQLLM
                break

        return ActionResponse(
            action=final_action,
            result="; ".join(contents) if contents else None,
            response="; ".join(responses_text) if responses_text else None,
        )

    async def register_iot_tools(self, descriptors: List[Dict[str, Any]]):
        """注册IoT设备工具"""
        self.device_iot_executor.register_iot_tools(descriptors)
        self.tool_manager.refresh_tools()
        self.logger.info(f"注册了{len(descriptors)}个IoT设备的工具")

    def get_tool_statistics(self) -> Dict[str, int]:
        """获取工具统计信息"""
        return self.tool_manager.get_tool_statistics()

    async def cleanup(self):
        """清理资源"""
        try:
            await self.server_mcp_executor.cleanup()

            # Clean up MCP endpoint connection
            if (
                hasattr(self.conn, "mcp_endpoint_client")
                and self.conn.mcp_endpoint_client
            ):
                await self.conn.mcp_endpoint_client.close()

            self.logger.info("工具处理器清理完成")
        except Exception as e:
            self.logger.error(f"工具处理器清理失败: {e}")
