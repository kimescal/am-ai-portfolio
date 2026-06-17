from typing import Optional, List
from pydantic import BaseModel

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langgraph.graph import END, START, StateGraph

from core import get_model, settings
from agents.portfolio.state import PortfolioFilter, PortfolioSelectionState

SYSTEM_PROMPT = f"""
# 核心职责
精选推荐结果

# 输出
从推荐结果中精选至多三只组合, 挑选原则为契合需求或者产品亮点突出. 给出推荐理由

# 限制
- 挑选出来的组合需阐述推荐理由, 描述简明扼要
- 精选结果不要以表格形式展现
"""

def summary(state: PortfolioSelectionState, config: RunnableConfig):
    response = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL)) \
        .invoke([SystemMessage(SYSTEM_PROMPT)] + state["messages"])

    return {"messages": [response]}


builder = StateGraph(PortfolioSelectionState)
builder.add_node("summary", summary) \
    .add_edge(START, "summary") \
    .add_edge("summary", END)

summary_agent = builder.compile()
