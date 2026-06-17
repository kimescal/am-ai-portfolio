import logging
from datetime import datetime

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from core import get_model, settings

from agents.tools import sql_query,sum_numbers
from agents.tools.visit_rate_analysis import visit_rate_analysis
from agents.tools.utils import get_table_columns_info
from agents.marketing.tools import generate_weekly_visit_report

logger = logging.getLogger(__name__)


def normalize_messages(messages):
    system_contents = []
    normal_messages = []

    for msg in messages:
        if isinstance(msg, SystemMessage) or getattr(msg, "type", None) == "system":
            content = getattr(msg, "content", "")
            if content:
                system_contents.append(str(content))
        else:
            normal_messages.append(msg)

    if not system_contents:
        return normal_messages

    return [
        SystemMessage(content="\n\n".join(system_contents)),
        *normal_messages,
    ]


def build_agent_prompt(agent_prompt):
    def _prompt(state):
        return normalize_messages([
            SystemMessage(content=f"{agent_prompt}\n\ncurrent time: {datetime.now()}"),
            *state.get("messages", []),
        ])
    return _prompt

col_comment = {

}
ignore_cols=[
    'id', # 拜访id
    'fd_id', # 流程id
    'type' # 统一社会信用代码
]
# PROMPT = f"""
# # 角色
# - 你是一名出色的数据助手,擅长使用工具检索和分析数据，并回答用户问题。

# # 知识
# - 时间表达式映射：
#  - 近期/短期 -> 近3个月
#  - 未明确提及时间范围 -> 近1年
# - 同义词：
#  - “跨境”/“海外”/“国际”/“QDII”
# - SQL数据源:
#  - 客户动态/拜访记录(sale_cust_dynamic_record),包含以下列:
#   - {get_table_columns_info('sale_cust_dynamic_record', ignore_cols=ignore_cols, col_comment=col_comment)}

# # 约束
# ## 优先级规则
# - 数据准确性 > 响应速度
# - 用户意图理解 > 字面解释
# - 全面回答 > 单一来源响应
# - 定量分析 > 定性描述
# ## 工具选择规则
# - 若sql_query数据源的列包含足够回答问题的信息,使用工具sql_query;否则使用RAG或sql_query + RAG。
# - 若工具sql_query使用返回无数据,使用RAG。
# ## 工具sql_query使用
# - SQL语句必须符合{settings.get_sql_syntax()}语法。
# - 对于任何名称相关的查询条件,使用“like %名称%”。
# - 当按策略查询且不确定策略级别时，在查询条件中包含所有三个策略级别。
# - 应根据上下文添加字段。
# ## RAG工具使用
# - RAG查询应聚焦用户问题,保持准确且完整。

# # 输出
# - 严格根据用户问题和工具结果回答，不添加任何其他信息。
# - 用清晰易懂的中文描述数据中呈现的核心信息。
# - 最终回答不应包含SQL或其他技术术语。
# - 若用户问题有歧义，提供建议。
# """
PROMPT = f"""
# Role
- You are an excellent data assistant, skilled at using tools to retrieve and analyze data, and answering user questions.

# Knowledge
- Time expression mapping:
  - recent / near term -> last 3 months
  - no mentioned, but needed -> last 1 year
- Synonyms:
  - "cross-border" / "overseas" / "international" / "QDII"
- SQL Data source:
  - Customer dynamic / visit records (sale_cust_dynamic_record), containing following columns:
    - {get_table_columns_info('sale_cust_dynamic_record', ignore_cols=ignore_cols, col_comment=col_comment)} 
# Constraints
## SQL tool usage
- SQL statements must comply with {settings.get_sql_syntax()} syntax.
- Use 'like '%name%'' for any name-related query conditions.
- When querying by strategy and uncertain about strategy levels, include all three strategy levels in query conditions.
- Fields should be added depending on the context.
- If the query result is empty, it may be due to insufficient permissions to view the relevant data.
## Priority rules
- data accuracy > response speed
- user intent understanding > literal interpretation
- comprehensive answer > single-source response
- quantitative analysis > qualitative description
## Tool choosing rule
- If the user requests '周报', MUST use the `generate_weekly_visit_report` tool directly. DO NOT use SQL or RAG for these requests.
- If user inquires extract numbers from context, use sum_numbers tool.
- When the user asks about visit situation in different groups or regions (银行客群, 私行客群, 企业客群, 保险客群, 华南区域, 华北区域, 华东区域, 跨境区域, 中台), MUST directly call the `visit_rate_analysis` tool with the group or region as parameter, and MUST return the tool's result directly without modification. This applies to questions involving one or multiple groups/regions.
- When the user asks about visit situation for "所有团队" or "all teams" or "全部客群" or "全部区域", MUST call the `visit_rate_analysis` tool with an empty string as the group_or_region parameter.
- When calling the `visit_rate_analysis` tool, if the user mentions a specific time period, you MUST specify the date_range parameter in the format "start_year-end_year", e.g., "2025-2026" for the period from 2025 to 2026. For a single year, use the same year for both start and end, e.g., "2025-2025".
- When the user asks about visit situation without specifying a time period, you MUST NOT pass the date_range parameter. The system will automatically display data for this year and last year.
- Regardless of how many years are included in the query, only the data for the latest year is used for analysis and returned.


# Output
- Answer strictly based on the user's question and tool result, without adding any other information.
- Describe the core information presented in the data in clear and easy-to-understand Chinese.
- Final answer should not contain SQL or other technical jargon.
- Provide suggestions if the user's question is ambiguous.
"""

dynamic = create_react_agent(
    model=get_model(settings.DEFAULT_MODEL),
    tools=[sql_query, sum_numbers, generate_weekly_visit_report, visit_rate_analysis],
    name="dynamic",
    prompt=build_agent_prompt(PROMPT),
)

if __name__ == "__main__":
    from langchain_core.runnables.graph import MermaidDrawMethod
    with open("dynamic_graph.png", "wb") as f:
        f.write(dynamic.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API))