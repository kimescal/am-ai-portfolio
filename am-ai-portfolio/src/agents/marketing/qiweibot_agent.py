import logging
from datetime import datetime

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import SystemMessage

from core import get_model, settings
from agents.tools.qiwei_tool import qiwei_success_tool

logger = logging.getLogger(__name__)

PROMPT = """
# 角色
- 你是一个企业微信助理，主要负责帮助用户发送智域测试数据、人物画像和拜访情况信息给对应的人。

# 处理逻辑
- 当收到包含@人名并且后面跟上"发送智域测试数据"、"发送人物画像"或"发送拜访情况"类似信息的消息时，你会处理相关请求
- 请提取所有@的人名，并将它们作为参数传递给qiwei_success_tool工具
- 只有当消息中同时包含@人名和上述提示词之一时，才执行工具调用
"""

@wrap_model_call
async def add_runtime_info(request,handler):
    request.messages.insert(
        1,
        SystemMessage(f"current time: {datetime.now()}")
    )
    return await handler(request)

qiwei = create_agent(
    model=get_model(settings.DEFAULT_MODEL),
    tools=[qiwei_success_tool],
    name="qiwei",
    system_prompt=PROMPT
)