import requests
from requests.exceptions import RequestException
from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.agent_id = config.get("agent_id")  # Corresponding agent_id
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", config.get("url"))  # Default to base_url
        self.api_url = f"{self.base_url}/api/conversation/process"  # Build full API URL

    def response(self, session_id, dialogue, **kwargs):
        try:
            # Home Assistant handles intents natively, so just forward the user's utterance

            # Extract content of the last message with role 'user'
            input_text = None
            if isinstance(dialogue, list):  # Ensure dialogue is a list
                # Traverse in reverse to find the last message with role 'user'
                for message in reversed(dialogue):
                    if message.get("role") == "user":  # Found message with role 'user'
                        input_text = message.get("content", "")
                        break  # Exit loop immediately once found

            # Build request payload
            payload = {
                "text": input_text,
                "agent_id": self.agent_id,
                "conversation_id": session_id,  # Use session_id as conversation_id
            }
            # Set request headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Send POST request
            response = requests.post(self.api_url, json=payload, headers=headers)

            # Check if request succeeded
            response.raise_for_status()

            # Parse response data
            data = response.json()
            speech = (
                data.get("response", {})
                .get("speech", {})
                .get("plain", {})
                .get("speech", "")
            )

            # Return generated content
            if speech:
                yield speech
            else:
                logger.bind(tag=TAG).warning("API 返回数据中没有 speech 内容")

        except RequestException as e:
            logger.bind(tag=TAG).error(f"HTTP 请求错误: {e}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"生成响应时出错: {e}")

    def response_with_functions(self, session_id, dialogue, functions=None):
        logger.bind(tag=TAG).error(
            f"homeassistant不支持（function call），建议使用其他意图识别"
        )
