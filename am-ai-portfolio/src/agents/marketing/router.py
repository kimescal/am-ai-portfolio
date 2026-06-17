import logging
import json
import os
from typing import Annotated, Literal, Sequence, TypedDict, Union, Any, Coroutine

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, SystemMessage, AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig


from agents.marketing.supervisor import supervisor

from agents.marketing.qiweibot_agent import qiwei
from agents.marketing.nodes import intent_guard as base_intent_guard, route_after_guard, GuardResult, reject_reply
from core import get_model, settings

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

from typing import Literal, Optional
from typing_extensions import TypedDict


# 定义 State，包含 current_agent 字段用于跟踪当前活跃处理者
class AgentState(TypedDict, total=False):
    """`total=False` is PEP589 specs."""
    messages: Annotated[Sequence[AnyMessage], add_messages]
    guard_result: GuardResult
    current_agent: str


def get_user_name_from_id(user_id: str) -> str:
    """从用户ID获取用户姓名"""
    try:
        from agents.tools.sql_query import sql_query
        import json
        query = f"SELECT NAME FROM emp_key_info WHERE BADGE = '{user_id}'"
        result = sql_query.invoke({"query": query})
        result_data = json.loads(result)
        
        if isinstance(result_data, list) and len(result_data) > 0 and 'NAME' in result_data[0]:
            return result_data[0]['NAME']
        return user_id
    except Exception as e:
        logger.error(f"Failed to get user name for {user_id}: {e}")
        return user_id

def check_user_in_whitelist(user_id: str) -> bool:
    """检查用户是否在白名单中（根据人名）"""
    # 获取白名单人名列表
    whitelist_names = settings.VISIT_WHITELIST_NAMES_LIST
    if not whitelist_names:
        logger.warning("VISIT_WHITELIST_NAMES is not configured")
        return False
    
    # 将user_id转换为人名
    user_name = get_user_name_from_id(user_id)
    
    # 检查用户姓名是否在白名单中
    if user_name in whitelist_names:
        return True
    
    logger.warning(f"User {user_name} ({user_id}) is not in VISIT_WHITELIST_NAMES")
    return False


def intent_guard(state: AgentState, config: RunnableConfig):
    """Router 专用意图识别节点（包含白名单检查）"""
    userId = config.get("metadata").get("user_id")
    messages = state["messages"]
    user_text = messages[-1].content if messages else ""

    # 检查用户是否在白名单中
    if not check_user_in_whitelist(userId):
        logger.warning(f"User {userId} is not in any whitelist, blocking access")
        return {"guard_result": GuardResult(action="block", reason="用户不在白名单中")}

    # 调用通用的意图识别
    return base_intent_guard(state, config)
async def supervisor_node(state: AgentState) -> Command | dict | dict[str, list[AIMessage]]:
    """Supervisor 节点：用于首轮分流或需要重新分流时使用"""
    # 检查是否需要 handoff 到 qiwei
    if "@AI资管营销助理" in state["messages"][-1].content:
        # 保留原始消息，并添加切换通知
        return Command(
            goto="qiwei",
            update={
                "current_agent": "qiwei",
                "messages": [AIMessage(content="已切换到AI资管营销助理，继续为您服务...")]
            }
        )

    # 否则调用 supervisor
    try:
        response = await supervisor.ainvoke(state)
        # 确保返回的是 dict，而不是协程
        if isinstance(response, dict):
            return response
        return {"messages": [AIMessage(content="抱歉，处理您的请求时出现错误。")]}
    except Exception as e:
        logger.error(f"Supervisor error: {e}")
        return {"messages": [AIMessage(content="抱歉，处理您的请求时出现错误。")]}

async def qiwei_node(state: AgentState) -> Command | dict | dict[str, list[AIMessage]] | dict[
    str, str | list[AIMessage]]:
    """资管营销助手节点：处理包含 '@资管营销助手' 的消息"""
    try:
        if "@总代理智能体" in state["messages"][-1].content:
            # 保留原始消息，并添加切换通知
            return Command(
                goto="supervisor",
                update={"current_agent": "supervisor",
                        "messages": [AIMessage(content="已切换回资管总智能体，继续为您服务...")]}

            )

        response = await qiwei.ainvoke(state)

        if isinstance(response, dict):
            return response
        return {"messages": [AIMessage(content="抱歉，处理您的请求时出现错误。")]}
    except Exception as e:
        logger.error(f"Qiwei error: {e}")
        # 保留原始消息，并添加切换通知
        return {
            "current_agent": "supervisor",
            "__goto__": "supervisor",
            "messages": [AIMessage(content="已切换回主管助手，继续为您服务...")]
        }

# 创建 StateGraph
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("qiwei", qiwei_node)
workflow.add_node("intent_guard", intent_guard)
workflow.add_node("route_after_guard", route_after_guard)
workflow.add_node("reject_reply", reject_reply)

# 添加条件路由函数
def route_start(state: AgentState) -> Literal["supervisor", "qiwei"]:
    """根据 current_agent 状态决定初始节点"""
    current_agent = state.get("current_agent")
    if current_agent == "qiwei":
        return "qiwei"
    return "supervisor"

# 设置入口点为条件路由
workflow.add_edge(START, "intent_guard")
workflow.add_conditional_edges("intent_guard", route_after_guard)
workflow.add_edge("supervisor", END)
workflow.add_edge("reject_reply", END)

# 编译图
router_agent = workflow.compile()

if __name__ == "__main__":
    from langchain_core.runnables.graph import MermaidDrawMethod
    with open("supervisor_graph.png", "wb") as f:
        f.write(router_agent.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API))

    # from IPython.display import display, Image
    # display(Image(agent_graph.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API)))

    # print(agent_graph.get_graph().draw_mermaid())
    # print(agent_graph.get_graph().print_ascii())