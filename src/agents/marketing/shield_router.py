import logging
from typing import Annotated, Literal, Sequence, TypedDict, Any

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from agents.marketing.supervisor import supervisor
from agents.marketing.nodes import intent_guard, GuardResult, reject_reply
from security import ShieldClient, ShieldResult

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    """`total=False` is PEP589 specs."""
    messages: Annotated[Sequence[AnyMessage], add_messages]
    pre_shield_passed: bool
    pre_shield_message: str
    post_shield_passed: bool
    post_shield_message: str
    shield_replaced_content: str | None
    guard_result: GuardResult


def pre_shield_check(state: AgentState, config: RunnableConfig) -> dict:
    """询问前电子围栏校验 - 在supervisor之前进行内容安全审核"""
    messages = state.get("messages", [])
    if not messages:
        return {"pre_shield_passed": True, "pre_shield_message": "无消息内容"}
    
    user_text = messages[-1].content if messages else ""
    
    try:
        shield_client = ShieldClient.get_instance()
        result: ShieldResult = shield_client.moderate(user_text)
        
        if not result.success:
            logger.warning(f"Pre-shield check failed: {result.error_message}")
            return {
                "pre_shield_passed": False,
                "pre_shield_message": result.error_message or "审核服务异常"
            }
        
        if not result.passed:
            logger.warning(f"Pre-shield blocked: {result.message}")
            return {
                "pre_shield_passed": False,
                "pre_shield_message": result.message
            }
        
        logger.info("Pre-shield check passed")
        return {
            "pre_shield_passed": True,
            "pre_shield_message": result.message,
            "shield_replaced_content": result.replaced_content
        }
    
    except Exception as e:
        logger.error(f"Pre-shield check exception: {e}")
        return {
            "pre_shield_passed": False,
            "pre_shield_message": str(e)
        }


def post_shield_check(state: AgentState, config: RunnableConfig) -> dict:
    """访问后电子围栏校验 - 在supervisor之后对响应内容进行安全审核"""
    messages = state.get("messages", [])
    if not messages:
        return {"post_shield_passed": True, "post_shield_message": "无消息内容"}
    
    # 获取最后一条AI响应消息
    ai_response = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            ai_response = msg.content
            break
    
    if not ai_response:
        return {"post_shield_passed": True, "post_shield_message": "无AI响应内容"}
    
    try:
        shield_client = ShieldClient.get_instance()
        result: ShieldResult = shield_client.moderate(ai_response)
        
        if not result.success:
            logger.warning(f"Post-shield check failed: {result.error_message}")
            return {
                "post_shield_passed": False,
                "post_shield_message": result.error_message or "审核服务异常",
                "messages": [AIMessage(content="系统检测到响应内容存在安全风险，已拦截。")]
            }
        
        if not result.passed:
            logger.warning(f"Post-shield blocked: {result.message}")
            return {
                "post_shield_passed": False,
                "post_shield_message": result.message,
                "messages": [AIMessage(content="系统检测到响应内容存在安全风险，已拦截。")]
            }
        
        # 如果内容被替换，使用替换后的内容
        if result.replaced_content:
            logger.info("Post-shield content replaced")
            # 替换最后一条AI消息的内容
            new_messages = []
            replaced = False
            for msg in messages:
                if isinstance(msg, AIMessage) and not replaced:
                    new_messages.append(AIMessage(content=result.replaced_content))
                    replaced = True
                else:
                    new_messages.append(msg)
            return {
                "post_shield_passed": True,
                "post_shield_message": result.message,
                "messages": new_messages
            }
        
        logger.info("Post-shield check passed")
        return {
            "post_shield_passed": True,
            "post_shield_message": result.message
        }
    
    except Exception as e:
        logger.error(f"Post-shield check exception: {e}")
        return {
            "post_shield_passed": False,
            "post_shield_message": str(e),
            "messages": [AIMessage(content="系统检测到响应内容存在安全风险，已拦截。")]
        }


def pre_shield_reject(state: AgentState) -> dict:
    """前电子围栏校验失败时的拒绝回复"""
    message = state.get("pre_shield_message", "您的请求存在安全风险，无法处理。")
    return {"messages": [AIMessage(content=message)]}


async def supervisor_node(state: AgentState) -> dict:
    """Supervisor节点"""
    try:
        # 如果有替换后的内容，使用替换后的内容作为用户输入
        replaced_content = state.get("shield_replaced_content")
        if replaced_content:
            # 创建新的消息列表，将最后一条用户消息替换为审核后的内容
            new_messages = []
            for msg in state["messages"]:
                if msg == state["messages"][-1]:  # 最后一条是用户消息
                    new_messages.append(type(msg)(content=replaced_content))
                else:
                    new_messages.append(msg)
            state = {"messages": new_messages}
        
        response = await supervisor.ainvoke(state)
        
        if isinstance(response, dict):
            return response
        return {"messages": [AIMessage(content="抱歉，处理您的请求时出现错误。")]}
    except Exception as e:
        logger.error(f"Supervisor error: {e}")
        return {"messages": [AIMessage(content="抱歉，处理您的请求时出现错误。")]}


# 创建 StateGraph
workflow = StateGraph(AgentState)

# 添加节点（使用 router.py 中的意图识别组件）
workflow.add_node("intent_guard", intent_guard)           # 从 router.py 导入
workflow.add_node("pre_shield_check", pre_shield_check)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("post_shield_check", post_shield_check)
workflow.add_node("pre_shield_reject", pre_shield_reject)
workflow.add_node("reject_reply", reject_reply)           # 从 router.py 导入

def route_after_pre_shield_to_intent(state: AgentState) -> Literal["intent_guard", "pre_shield_reject"]:
    """前电子围栏通过后进入意图识别"""
    passed = state.get("pre_shield_passed")
    if passed:
        return "intent_guard"
    return "pre_shield_reject"


def route_after_intent_to_supervisor(state: AgentState) -> Literal["supervisor", "reject_reply"]:
    """意图识别通过后进入supervisor"""
    guard_result = state.get("guard_result")
    if guard_result and guard_result.action == "allow":
        return "supervisor"
    return "reject_reply"


# 添加边
workflow.add_edge(START, "pre_shield_check")
workflow.add_conditional_edges("pre_shield_check", route_after_pre_shield_to_intent)
workflow.add_edge("pre_shield_reject", END)
workflow.add_conditional_edges("intent_guard", route_after_intent_to_supervisor)
workflow.add_edge("reject_reply", END)
workflow.add_edge("supervisor", "post_shield_check")
workflow.add_edge("post_shield_check", END)

# 编译图
shield_router_agent = workflow.compile()


if __name__ == "__main__":
    from langchain_core.runnables.graph import MermaidDrawMethod
    with open("shield_router_graph.png", "wb") as f:
        f.write(shield_router_agent.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API))
