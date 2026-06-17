from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages import (
    ChatMessage as LangchainChatMessage,
)

from schema import ChatMessage


def convert_message_content_to_string(content: str | list[str | dict]) -> str:
    if isinstance(content, str):
        return content
    text: list[str] = []
    for content_item in content:
        if isinstance(content_item, str):
            text.append(content_item)
            continue
        if content_item["type"] == "text":
            text.append(content_item["text"])
    return "".join(text)


def langchain_to_chat_message(message: BaseMessage) -> ChatMessage:
    """Create a ChatMessage from a LangChain message."""
    match message:
        case HumanMessage():
            human_message = ChatMessage(
                type="human",
                content=convert_message_content_to_string(message.content),
            )
            return human_message
        case AIMessage():
            ai_message = ChatMessage(
                type="ai",
                content=convert_message_content_to_string(message.content),
            )
            # 优先使用message.tool_calls，如果没有则检查additional_kwargs
            if message.tool_calls:
                ai_message.tool_calls = message.tool_calls
            elif hasattr(message, 'additional_kwargs') and message.additional_kwargs:
                # 检查additional_kwargs中是否有tool_calls信息
                if 'tool_calls' in message.additional_kwargs:
                    ai_message.tool_calls = message.additional_kwargs['tool_calls']
                # 检查是否有其他格式的tool calls信息
                elif 'function_call' in message.additional_kwargs:
                    # 处理function_call格式的tool calls
                    function_call = message.additional_kwargs['function_call']
                    if function_call:
                        # 解析arguments字符串为字典
                        arguments_str = function_call.get('arguments', '{}')
                        try:
                            import json
                            arguments_dict = json.loads(arguments_str) if arguments_str else {}
                        except json.JSONDecodeError:
                            arguments_dict = {}
                        
                        # 生成有效的tool call id
                        import uuid
                        tool_call_id = str(uuid.uuid4())
                        
                        ai_message.tool_calls = [{
                            'name': function_call.get('name', ''),
                            'args': arguments_dict,
                            'id': tool_call_id,
                            'type': 'tool_call'
                        }]
            
            if message.response_metadata:
                ai_message.response_metadata = message.response_metadata
            return ai_message
        case ToolMessage():
            tool_message = ChatMessage(
                type="tool",
                content=convert_message_content_to_string(message.content),
                tool_call_id=message.tool_call_id,
            )
            return tool_message
        case LangchainChatMessage():
            if message.role == "custom":
                custom_message = ChatMessage(
                    type="custom",
                    content="",
                    custom_data=message.content[0],
                )
                return custom_message
            else:
                raise ValueError(f"Unsupported chat message role: {message.role}")
        case SystemMessage():
            # SystemMessage 来自 supervisor 的系统提示词，admin 页面不需要显示
            return ChatMessage(type="ai", content="")
        case _:
            raise ValueError(f"Unsupported message type: {message.__class__.__name__}")


def remove_tool_calls(content: str | list[str | dict]) -> str | list[str | dict]:
    """Remove tool calls from content."""
    if isinstance(content, str):
        return content
    # Currently only Anthropic models stream tool calls, using content item type tool_use.
    return [
        content_item
        for content_item in content
        if isinstance(content_item, str) or content_item["type"] != "tool_use"
    ]
