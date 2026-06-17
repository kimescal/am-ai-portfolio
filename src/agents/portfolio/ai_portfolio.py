
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agents.portfolio.market_data_expert import market_data_expert
from agents.portfolio.strategy_judger import strategy_judger
from agents.portfolio.portfolio_judger import portfolio_judger
from agents.portfolio.summary_expert import summary_agent
from agents.portfolio.portfolio_aggregator import portfolio_aggregator

from agents.portfolio.tools.amcell import portfolio_filter

from agents.portfolio.state import PortfolioSelectionState

def call_portfolio_aggregator(state: PortfolioSelectionState, config: RunnableConfig):
    aggregator_state = portfolio_aggregator.invoke({"filter": state})
    return {"messages": [AIMessage(content=aggregator_state["portfolios_markdown"], name="portfolio_aggregator")]}

builder = StateGraph(PortfolioSelectionState)

builder.add_node("market_data_expert", market_data_expert)
builder.add_node("strategy_judge_agent", strategy_judger)
builder.add_node("portfolio_judge_agent", portfolio_judger)
builder.add_node("portfolio_selection", call_portfolio_aggregator)
builder.add_node("summary_agent", summary_agent)

builder.add_edge(START, "market_data_expert")
builder.add_edge(START, "strategy_judge_agent")
builder.add_edge(START, "portfolio_judge_agent")
builder.add_edge("market_data_expert", "portfolio_selection")
builder.add_edge("strategy_judge_agent", "portfolio_selection")
builder.add_edge("portfolio_judge_agent", "portfolio_selection")
builder.add_edge("portfolio_selection", "summary_agent")
builder.add_edge("summary_agent", END)

ai_portfolio =  builder.compile()



# "请帮我查找ID为‘PD-AMC-2018-00275’的组合",
#"请帮我查找马艳管理的固收组合，风险等级R2，最多提供5个",
# "请提供纯债策略产品，风险等级R2，投资经理马艳，近三年年化5%以上，同期存款收益+50bp",
# "请提供固收+产品，增强部分可投资转债或权益类资产，风险等级R2",
# "目标收益为同期存款收益+50bp，波动尽可能小，不能投转债，1亿以上规模，近三年年化3%以上",
# "内部信用债小集合不含永续",
# "条件如下：1. AA比例不超30%（当前持仓，非合同条款）2. 无地产债、无永续债（实际投资以及未来投资不涉及，非合同条款）3.信用债久期3年以内（利率债交易型久期不算） 4. 可以接受月初进、月末走，流动性灵活 5. 月内跑赢同业资金成本（目前1.6%）6.实际投资不包括转债、权益、国债期货等衍生品。",
# "客户现想通过期货资管计划投向我们的产品，因此需要我们现有的、可投的后端底层，客户费后收益目标4-4.5%。现需要能现投的、业绩基准4%以上的固收+后端集合",
# "美元债产品推荐",
# "请提供REITs及固收+REITs策略产品，每周开放，风险等级R3以内，1亿以上规模，近三年年化1%以上",
# "请提供REITs及固收+REITs策略产品，每季度开放，风险等级R4以内",
# "请提供固收+国债期货产品，风险等级R3以内，投资经理马艳，不含转债",