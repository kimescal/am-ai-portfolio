import logging
from datetime import datetime

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from core import get_model, settings

from agents.tools import sql_query,sum_numbers
from agents.tools.utils import get_table_columns_info
from agents.tools.rag_api import query_rag_api

logger = logging.getLogger(__name__)

col_comment = {
    'project_name': '项目名称',
    'customer_level': '客户级别',
    'customer_short_name': '客户简称',
    'customer_segment': '客群',
    'region': '区域',
    'owners': '负责人（逗号分隔）',
    'base_target_amount': '基础目标（亿元）',
    'stretch_target_amount': '进阶目标（亿元）',
    'status': '状态',
    'created_by': '创建人',
    'created_at': '创建时间',
    'updated_by': '更新人',
    'updated_at': '更新时间'
}

ignore_cols = [
    'id', # 主键
    'creator', # 创建人
    'create_time', # 创建时间
    'updater', # 更新人
    'update_time', # 更新时间
]

PROMPT = f"""
# Role
- You are an excellent data assistant, skilled at using tools to retrieve and analyze data, and answering user questions.

# Knowledge
- Time expression mapping:
  - recent / near term -> last 3 months
  - 今年 / this year -> current year
  - 未明确提及时间范围 -> current year
- Business goal plan table structure:
  - business_goal_plan, with columns:
    - {get_table_columns_info('business_goal_plan', ignore_cols=ignore_cols, col_comment=col_comment)}
- Status classification:
  - 已落地
  - 已覆盖
  - 签约中
  - 未覆盖
  - 已签约
# Constraints
## Priority rules
- data accuracy > response speed
- user intent understanding > literal interpretation
- comprehensive answer > single-source response
- quantitative analysis > qualitative description
## Tool usage
- SQL statements must comply with {settings.get_sql_syntax()} syntax.
- Use 'like '%name%'' for any name-related query conditions.
- When querying by customer segment, region, or status, use exact matching if possible.
- Fields should be added based on the context.
- If the query result is empty, it may be due to insufficient permissions to view the relevant data.
- When performing sum operations or other aggregate calculations, use SQL aggregate functions (such as SUM, AVG, COUNT, MAX, MIN) instead of manual calculations.
## RAG tool usage
- Query about customer names or project names, use SQL first; if not found, use RAG and list all similar results mentioned.

# Output
- Answer strictly based on the user's question and tool result, without adding any other information.
- Describe the core information presented in the data in clear and easy-to-understand Chinese.
- Final answer should not contain SQL or other technical jargon.
- Provide suggestions if the user's question is ambiguous.
"""

# 提示词翻译注释
# ==================

# Role（角色）
# - 你是一位优秀的数据助手，擅长使用工具检索和分析数据，并回答用户问题。

# Knowledge（知识）
# - Time expression mapping（时间表达式映射）:
#   - recent / near term -> last 3 months（近期 -> 最近3个月）
#   - 今年 / this year -> current year（今年 -> 当前年份）
#   - 未明确提及时间范围 -> current year（未明确提及时间范围 -> 当前年份）
# - Business goal plan table structure（业务目标计划表结构）:
#   - business_goal_plan表，包含以下列：
#     - 项目名称、客户级别、客户简称、客群、区域、负责人（逗号分隔）、基础目标（亿元）、进阶目标（亿元）、状态
# - Status classification（状态分类）:
#   - 已落地
#   - 已覆盖
#   - 签约中
#   - 未覆盖
#   - 已签约

# Constraints（约束条件）
# Priority rules（优先级规则）
# - data accuracy > response speed（数据准确性 > 响应速度）
# - user intent understanding > literal interpretation（用户意图理解 > 字面解释）
# - comprehensive answer > single-source response（全面回答 > 单一来源响应）
# - quantitative analysis > qualitative description（定量分析 > 定性描述）

# Tool usage（工具使用）
# - SQL语句必须符合{settings.get_sql_syntax()}语法。
# - 对任何与名称相关的查询条件使用'like '%name%''。
# - 当按客户细分、区域或状态查询时，尽可能使用精确匹配。
# - 应根据上下文添加字段。
# - 如果查询结果为空，可能是由于查看相关数据的权限不足。
# - 当执行求和操作或其他聚合计算时，应使用SQL聚合函数（如SUM、AVG、COUNT、MAX、MIN），而不是手动计算。

## RAG tool usage
# - 关于客户名称或项目名称的查询，首先使用SQL；如果未找到，使用RAG并列出所有提到的类似结果。

# Output（输出）
# - 严格根据用户的问题和工具结果回答，不添加任何其他信息。
# - 用清晰易懂的中文描述数据中呈现的核心信息。
# - 最终答案不应包含SQL或其他技术术语。
# - 如果用户的问题含糊不清，请提供建议。

business_goal = create_react_agent(
    model=get_model(settings.DEFAULT_MODEL),
    tools=[sql_query, query_rag_api],
    name="business_goal",
    prompt=lambda state: [SystemMessage(PROMPT), SystemMessage(f"current time: {datetime.now()}")] + state["messages"],
)

if __name__ == "__main__":
    from langchain_core.runnables.graph import MermaidDrawMethod
    with open("business_goal_graph.png", "wb") as f:
        f.write(business_goal.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API))

# 示例问题：
# 1. 银行理财的今年的业务目标
# 2. 江苏银行的业务目标
# 3. 江苏银行的客户画像
# 4. 王文轩负责的项目