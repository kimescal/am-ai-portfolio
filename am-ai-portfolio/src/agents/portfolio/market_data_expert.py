import json
from typing import Optional
from pydantic import BaseModel

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from core import get_model, settings

from agents.portfolio.state import MarketDataBenchmark, PortfolioSelectionState
from agents.portfolio.tools.market_data import market_data

SYSTEM_PROMPT = f"""
# 核心职责: 分析用户需求, 利用工具获取基准收益率

# 限制
- 只有用户**明确**提及目标收益/基准收益, 才根据对应描述获取数据, 否则不用获取, 直接返回
- 所有数据必须来自工具
- 你的职责只是获取基准收益率, 严禁发散

# 背景知识
- 如果明确提及基准, 但未指定指标, 也未指定期限, 则选择三年期定期存款利率
- 如果明确提及基准, 且有指定指标, 但没有指定期限, 则期限使用一年期
"""

def retrieve_market_data(state: PortfolioSelectionState, config: RunnableConfig):
    response = (
        get_model(config["configurable"].get("model", settings.DEFAULT_MODEL)).bind_tools([market_data])
            .invoke([SystemMessage(SYSTEM_PROMPT)] + state["messages"], config)
    )

    return {"messages": [response]}

def call_market_data(state: PortfolioSelectionState):
    response = market_data.invoke(state["messages"][-1].tool_calls[0])
    if response.content and len(response.content) > 0:
        return {"market_data_benchmark": MarketDataBenchmark(**json.loads(response.content)[0])}

def should_continue(state: PortfolioSelectionState):
    if state["messages"][-1].tool_calls and state["messages"][-1].tool_calls[0]["name"] == "market_data":
        return True

    return False

builder = StateGraph(PortfolioSelectionState)

builder.add_node("retrieve_market_data", retrieve_market_data)
builder.add_node("call_market_data", call_market_data)

builder.add_edge(START, "retrieve_market_data")
builder.add_conditional_edges("retrieve_market_data", should_continue, {True: "call_market_data", False: END})
builder.add_edge("call_market_data", END)

market_data_expert = builder.compile()