import json
import logging
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from core import get_model, settings

from agents.tools import sql_query

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = f"""
# 核心职责: 根据用户问题, 生成符合{settings.get_sql_syntax()}语法的SQL查询语句

# 背景知识
- 当前时间是{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- 源数据表名固定为sale_cust_invest_requirement
- 源数据包含以下列: create_time(创建时间),operator(当前处理人),requirement_name(机构客户需求名称),cust_name(机构客户名称),cust_manager(客户经理名称),cust_invest_strategy(一级投资策略),second_invest_strategy_name(二级投资策略),third_invest_strategy_name(三级投资策略),update_time(更新时间),status(需求状态),modify_content(需求更新点),create_by(创建人),update_by(更新人),invest_manager_name(客户需求对应的投资经理),assignee(需求对接的主产品经理),backup_operator(对接的辅产品经理),return_reason(需求被退回的原因),return_operator(执行退回的产品经理)
- 模糊时间映射: 最近/近期 -> 近三月
- 同义词: 境外/海外/国际/跨境/QDII

# 限制
- 生成的SQL查询语句务必符合{settings.get_sql_syntax()}语法
- 任何查询条件中涉及名称的, 都使用like '%名称%'
- 如果要根据策略查询, 且不确定用几级策略的时候, 把三级策略都加到查询条件里

#输出
- 至少包含以下列: 创建时间, 客户名称, 需求名称, 一级策略, 二级策略, 三级策略, 投资经理, 客户经理, 需求状态
- 其他列根据用户问题酌情添加
"""

def analysis_question(state: MessagesState, config: RunnableConfig):
    response = (
        get_model(config["configurable"].get("model", settings.DEFAULT_MODEL)) \
            .bind_tools([sql_query]) \
            .invoke([SystemMessage(ANALYSIS_PROMPT)] + state["messages"], config)
    )

    # logger.debug(f"analysis_question response: {response}")
    return {"messages": [response]}

def should_continue(state: MessagesState):
    if state["messages"][-1].tool_calls and "sql_query" in state["messages"][-1].tool_calls[0]["name"]:
        return True

    return False

def call_query_requirement(state: MessagesState):
    response = sql_query.invoke(state["messages"][-1].tool_calls[0])

    # logger.debug(f"call_query_requirement response: {response}")
    return {"messages": [response]}


SUMMARIZW_PROMPT = f"""
# 核心职责: 根据用户问题和查询结果, 生成最终的结果

# 限制
- 回答只能基于用户问题和查询结果, 不得使用任何其他信息
- 回答不应包含sql等专业语言
- 请勿重复之前AI的回答

# 输出
- 输出结果需包含查询结果核心关键信息, 并有效回应用户问题
- 输出结果简洁凝练, 一般不超过500字.
- 如果前置AI的回答已经包含报错了, 无须重复输出报错信息, 可以根据报错信息, 生成调整提示.
"""

def summarize(state: MessagesState, config: RunnableConfig):
    response = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL)) \
        .invoke([SystemMessage(SUMMARIZW_PROMPT)] + state["messages"], config)

    logger.debug(f"summarize state messages: {state['messages']}")
    logger.debug(f"summarize response: {response}")
    return {"messages": [response]}

builder = StateGraph(MessagesState)

builder.add_node("analysis_question", analysis_question)
builder.add_node("call_query_requirement", call_query_requirement)
builder.add_node("summarize", summarize)

builder.add_edge(START, "analysis_question")
builder.add_conditional_edges("analysis_question", should_continue, {True: "call_query_requirement", False: END})
builder.add_edge("call_query_requirement", "summarize")
builder.add_edge("summarize", END)

requirement_QA = builder.compile()


# 民生理财上半年有什么需求？进度如何
# REITs策略还有哪些客户最近有关注