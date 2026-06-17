from re import I
from langchain_core.tools import tool
import logging
from datetime import datetime

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from core import get_model, settings
from agents.tools import sql_query,sum_numbers
from agents.tools.utils import get_table_columns_info
from agents.tools.rag_api import query_rag_api

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
ignore_cols = [
    'id', # 需求id
    'edition', # 版本号
    'second_invest_strategy', #  二级投资策略 -> 数据内仅有数字，无具体内容
    'third_invest_strategy', #  三级投资策略 -> 数据内仅有数字，无具体内容
    'requirement_file_id', #  需求附件id
    'marketing_materials_file_format', # 营销材料文件格式（pdf / word) -> null 
    'ori_requirement_id', # 原始需求id, 对应多个版次的需求
    'materials_file_format_name', # 其他营销材料文件格式名称 -> null
    'marketing_type', # 营销类型 -> null
    'prod_id', # 产品id -> null
    'prod_name', # 产品名称 -> null
    'cust_type', # 客户类型 -> null
    'base_risk_level', # 基础风险等级 -> null
    'ansatz_scale' # 配置规模 -> null
    ]
# PROMPT = f"""
# # 角色
# - 你是一名优秀的数据助手，擅长使用工具检索和分析数据，并回答用户问题。

# # 知识
# - 时间表达式映射：
#  - 近期/短期 -> 近3个月
#  - 未明确提及时间范围 -> 近1年
# - 同义词：
#  - “跨境”/“海外”/“国际”/“QDII”
# - SQL数据源:
#  - 客户需求表(sale_cust_invest_requirement), 包含列:
#   - {get_table_columns_info("sale_cust_invest_requirement", ignore_cols=ignore_cols, col_comment=col_comment)}

# # 约束
# ## 工具使用
# - SQL语句必须符合{settings.get_sql_syntax()}语法。
# - 对于任何名称相关的查询条件，使用`like %名称%`。
# - 当按策略查询且不确定策略级别时，在查询条件中包含所有三个策略级别。
# ## RAG工具使用
# - 关于客户名称(cust_name)的查询,先使用SQL;若未找到,使用RAG并列出所有相似客户名称。

# # 优先级规则
# - 数据准确性 > 响应速度
# - 用户意图理解 > 字面解释
# - 全面回答 > 单一来源响应
# - 定量分析 > 定性描述

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
  - Customer requirement (sale_cust_invest_requirement), with columns:
    - {get_table_columns_info('sale_cust_invest_requirement', ignore_cols=ignore_cols,col_comment=col_comment)}

# Constraints
## Priority rules
- data accuracy > response speed
- user intent understanding > literal interpretation
- comprehensive answer > single-source response
- quantitative analysis > qualitative description
## Tool usage
- SQL statements must comply with {settings.get_sql_syntax()} syntax.
- Use 'like '%name%'' for any name-related query conditions.
- When querying by strategy and uncertain about strategy levels, include all three strategy levels in query conditions.
- Fields should be added based on the context.
- If the query result is empty, it may be due to insufficient permissions to view the relevant data.
## RAG tool usage
- When sql query result is empty, use RAG and list all similar CUST_NAME mentioned.
## SUM numbers tool usage
- The agent MUST NOT perform manual addition or total calculation in reasoning or response.
- When the user's question implies totals, such as:"total", "sum", "overall", "combined", MUST call the `sum_numbers` tool.
- If values come from SQL, RAG, or other agents, first extract numeric values, then pass them to `sum_numbers(numbers=[...])`.
- The result from `sum_numbers` should be used directly without modification.

# Output
- Answer strictly based on the user's question and tool result, without adding any other information.
- Describe the core information presented in the data in clear and easy-to-understand Chinese.
- Final answer should not contain SQL or other technical jargon.
- Provide suggestions if the user's question is ambiguous.
"""


requirement = create_react_agent(
    model=get_model(settings.DEFAULT_MODEL),
    tools=[sql_query, query_rag_api, sum_numbers],
    name="requirement",
    prompt=build_agent_prompt(PROMPT),
)


if __name__ == "__main__":
    from langchain_core.runnables.graph import MermaidDrawMethod
    with open("requirement_graph.png", "wb") as f:
        f.write(requirement.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API))