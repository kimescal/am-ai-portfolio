from typing import Optional, List, Dict
from pydantic import BaseModel
from typing import List, Dict, Optional
import datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph, MessagesState

from agents.portfolio.tools.amcell import portfolio_filter, portfolio_performance

from agents.portfolio.state import PortfolioSelectionState

class AggregatorState(MessagesState):
    filter: Optional[PortfolioSelectionState] = None
    portfolios: List[Dict] = []
    portfolios_markdown: Optional[str] = None

def filter(state: AggregatorState, config: RunnableConfig):
    strategies = investor_names = full_names = risk_level = None
    filter = state["filter"]
    if filter["strategy_filter"] and filter["strategy_filter"].strategies:
        strategies = [item.model_dump() for item in filter["strategy_filter"].strategies]
    if filter["portfolio_filter"]:
        if filter["portfolio_filter"].investor_names:
            investor_names = filter["portfolio_filter"].investor_names
        if filter["portfolio_filter"].full_names:
            full_names = filter["portfolio_filter"].full_names
        if filter["portfolio_filter"].risk_level:
            risk_level = filter["portfolio_filter"].risk_level

    portfolios = portfolio_filter(strategies, investor_names, full_names, risk_level)

    return {"portfolios": portfolios}

def supply_info(state: AggregatorState, config: RunnableConfig):
    portfolios = state["portfolios"]
    end_dt_str = datetime.date.today().strftime('%Y-%m-%d')

    for p in portfolios:
        start_dt_str = p.get('start_dt')
        if start_dt_str:
            # 获取运作以来数据
            from_start_perf_data = portfolio_performance(
                portfolio_id_list=[p['id']],
                start_dt=start_dt_str,
                end_dt=end_dt_str
            )
            if from_start_perf_data and from_start_perf_data.get('data'):
                p['from_start_perf'] = from_start_perf_data['data'][0]
                # 计算运作以来年化收益
                from_start_return_rate = p['from_start_perf'].get('return_rate')
                if from_start_return_rate is not None:
                    start_dt = datetime.datetime.strptime(start_dt_str, '%Y-%m-%d').date()
                    today = datetime.date.today()
                    delta_days = (today - start_dt).days
                    if delta_days > 0:
                        annualized_return = (1 + from_start_return_rate)**(365 / delta_days) - 1
                        p['from_start_perf']['annualized_return'] = annualized_return

    return {"portfolios": portfolios}

def transform_markdown(state: AggregatorState, config: RunnableConfig):
    portfolios = state["portfolios"]

    if not portfolios:
        return {"portfolios_markdown": ""}

    # Define the columns for the markdown table
    # You can customize these based on the keys present in your portfolio dictionaries
    columns = [
        {"header": "ID", "key": "id"},
        {"header": "简称", "key": "prtfl_sim_nm"},
        {"header": "策略", "key": "strategy_name"},
        {"header": "起始日期", "key": "start_dt"},
        {"header": "规模(百万)", "key": "aum", "format": lambda x: f"{x/1_000_000:,.2f}" if x is not None else "-"},
        {"header": "风险等级", "key": "strategy_minimum_risk_level"},
        {"header": "投资经理", "key": "performance_investor_names", "format": lambda x: ", ".join(x) if isinstance(x, list) else str(x) if x is not None else "-"},
        {"header": "近1年收益率", "key": "recent_1y_perf.return_rate", "format": lambda x: f"{x:.2%}" if x is not None else "-"},
        {"header": "近1年最大回撤", "key": "recent_1y_perf.max_drawdown", "format": lambda x: f"{x:.2%}" if x is not None else "-"},
        {"header": "运作以来年化收益率", "key": "from_start_perf.annualized_return", "format": lambda x: f"{x:.2%}" if x is not None else "-"},
        {"header": "运作以来最大回撤", "key": "from_start_perf.max_drawdown", "format": lambda x: f"{x:.2%}" if x is not None else "-"},
    ]

    # Build the markdown table header
    header_line = "|" + "|".join([col["header"] for col in columns]) + "|"
    separator_line = "|" + "|".join(["---" for _ in columns]) + "|"

    # Build the markdown table rows
    data_lines = []
    for portfolio in portfolios:
        row_data = []
        for col in columns:
            value = portfolio
            # Navigate through nested keys
            for k in col["key"].split('.'):
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    value = None  # Handle missing keys gracefully
                    break

            formatted_value = str(value)
            if "format" in col and value is not None:
                formatted_value = col["format"](value)
            elif value is None:
                formatted_value = "-"
            row_data.append(formatted_value)
        data_lines.append("|" + "|".join(row_data) + "|")

    markdown_table = "\n".join([header_line, separator_line] + data_lines)

    return {"portfolios_markdown": markdown_table}


builder = StateGraph(AggregatorState)
builder.add_node("filter", filter)
builder.add_node("supply_info", supply_info)
builder.add_node("transform_markdown", transform_markdown)
builder.add_edge(START, "filter")
builder.add_edge("filter", "supply_info")
builder.add_edge("supply_info", "transform_markdown")
builder.add_edge("transform_markdown", END)

portfolio_aggregator =  builder.compile()
