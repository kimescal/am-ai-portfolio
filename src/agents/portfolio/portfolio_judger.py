from typing import Optional, List
from pydantic import BaseModel

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langgraph.graph import END, START, StateGraph

from core import get_model, settings
from agents.portfolio.state import PortfolioFilter, PortfolioSelectionState

SYSTEM_PROMPT = f"""
# 核心职责
分析用户需求, 提取用户感兴趣的投资组合要素

# 背景知识
- 用户如果提及这些关键字: FOF单一 / FOF集合 / FOF / 单一 / 集合, 则full_names需加入"FOF"
- 用户如果提及这些关键字: 低风险 / 中风险 / 高风险, 则risk_level需加入对应数值.

# 示例
- 输入: "我想投资FOF集合, 风险等级为R1"
  - 输出: {{"full_names": ["FOF集合"], "risk_level": 1}}
- 输入: "我想投资FOF组合, 风险等级为R1"
  - 输出: {{"full_names": ["FOF"], "risk_level": 1}}
- 输入: "内部信用债小集合不含永续, 风险等级为R2"
  - 输出: {{"full_names": ["集合"], "risk_level": 2}}
- 输入: "请帮我查找马艳管理的单一计划, 风险等级R2"
  - 输出: {{"full_names": ["单一"], "investor_names": ["马艳"], "risk_level": 2}}
"""

def portfolio_judge(state: PortfolioSelectionState, config: RunnableConfig):
    response = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL)) \
        .with_structured_output(PortfolioFilter) \
        .invoke([SystemMessage(SYSTEM_PROMPT)] + state["messages"], config)

    return {
        "portfolio_filter": response,
        "messages": [AIMessage(response.model_dump_json() if response else "")]
    }


builder = StateGraph(PortfolioSelectionState)
builder.add_node("portfolio_judge", portfolio_judge) \
    .add_edge(START, "portfolio_judge") \
    .add_edge("portfolio_judge", END)

portfolio_judger = builder.compile()
