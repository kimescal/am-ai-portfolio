import logging
from datetime import datetime, date

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from core import get_model, settings

from agents.tools import sql_query,sum_numbers
from agents.tools.utils import get_table_columns_info
from agents.marketing.tools import portfolio_range_performance
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

info_col_comment = {
}

info_ignore_cols = [
 'PERFORM_PAY_DESC'# '业绩报酬'
 'INVEST_ADVISOR_RATE'# '投顾费比例' -> null
 'OPEN_STATUS' #'今日开放状态' -> null,1,2
 'VALT_METHODS' #'估值方法（市值法/摊余成本法)' -> null,0,1
 'WARN_LIMIT' # '预警线'
 'STOP_LIMIT' # '止损线'
 'MINASSET' # '存续期规模上限' -> null, 0.00
 'BUSI_TYPE_PRODUCT' # '业务分类-产品组'
 'BUSI_TYPE_CONTRACT' # '业务分类-合同组' -> null
 'PRO_FEATURE' # '主要投向或策略特征' -> null
 'PROD_POST_AX' # '产品定位-是否安享后端' -> null
 'PROD_POST_DK' # '产品定位-是否大客定制后端' -> null
 'PROD_POST_OTHER' # '产品定位-其他' -> null
 'FUND_TERM' # '资金期限' -> null
 'FUND_OTHER' # '其他资金要求' -> null
 'CONTRACT_CHANGE_REQ' # '合同变更要求'
 'IN_CHANGE_DATE' # '拟变更开放期' -> null,0,不适用
 'IN_CHANGE_RISK_LEVEL' # '拟变更风险等级' -> null,0,不适用
 'IN_CHANGE_MG_FEE' # '拟变更管理费' -> null,0.001,不适用
 'IN_CHANGE_PERFORM_FEE' # '拟变更业绩报酬' -> null,4%以上计提20%,不适用
 'IN_CHANGE_BEGIN_DATE' # '拟变更生效日' -> null,2025-01-13,不适用
 'INVEST_CONTRACT_VERSION' # '投资范围-合同版本'
 'INVEST_LIMIT_CONTRACT_VERSION' # '投资比例限制-合同版本'
 'TEAM_NAME' # '团队名称'
 'CUSTOMER_GROUP_LEVEL3' # '客群三级分类' -> null
 'CUSTOMER_CLASS' # '客户分类' -> null
 'REMARK' # '备注' -> null
 'ITEM_CODE' # '财务段代码'
 'BUSINESS_CLASS' # '业务分类' -> null
 'C_INVEST_SCOPE' # '产品分类'
 'FOF_RATIO' # 'FOF占比' -> 容易造成歧义
]

performance_col_comment = {
}

performance_ignore_cols = [

]

# sale_prod_top_cust表的配置
sale_cust_col_comment = {
}

sale_cust_ignore_cols = [
]
# PROMPT = f"""
# # 角色
# - 你是一名出色且注重细节的数据分析专家，擅长使用工具查询和分析数据，并回答用户问题。

# # 背景知识
# - 母公司主要聚焦"养老金业务"，子公司聚焦其他业务：
#  - "母公司"/"中信证券" -> C_MANAGER_NEW = "母公司"
#  - "子公司"/"中信证券资产管理"/“中信证券资管”/"资管子公司"/"资管" -> C_MANAGER_NEW = "子公司"
# - 区分 "MANAGERS":
#  - 客户经理(CUST_MGR)负责服务客户。
#  - 产品经理(MANAGER)负责组合业绩的督导。
#  - 投资经理(KH_INVESTOR)负责组合的实际管理和跟踪，在讨论"谁管理的产品"或"谁的产品"时始终使用该字段。
# - 两个用于查询组合业绩的工具：
#  - sql_query_on_table_portfolio_performance:提供固定周期的业绩，包括 1 年（近一年，当前日期：{date.today ()})和年初至今(YTD)。
#  - portfolio_range_performance:提供任意时间范围的业绩。若按名称查询，使用 sql_query 查询 portfolio_performance 表以获取 ID。
#  - 若 sql_query 能回答问题则使用它,如若不能使用 portfolio_range_performance。
#  - 若 sql_query 失败,返回到 portfolio_range_performance。
# - 工具 sql_query 的数据库信息：
#  1. portfolio_info表,包含列：
#   - {get_table_columns_info('portfolio_info', ignore_cols=info_ignore_cols, col_comment=info_col_comment)}
#   - 重要说明：
#    - 当查询投资者 / 经理 / 投资经理时：优先使用 KH_INVESTOR,若为 NULL 则返回到 INVESTOR。
#  2. portfolio_performance表,包含列：
#    - {get_table_columns_info('portfolio_performance', ignore_cols=performance_ignore_cols, col_comment=performance_col_comment)}
#  3. sale_prod_top_cust表,包含列:
#    - {get_table_columns_info('sale_prod_top_cust', ignore_cols=sale_cust_ignore_cols, col_comment=sale_cust_col_comment)}
#    - 该表主要用于查询最大/主要持有人。

# # 约束
# ## 优先级规则
#   - 数据准确性 > 响应速度
#   - 用户意图理解 > 字面解释
#   - 全面回答 > 单一来源响应
#   - 定量分析 > 定性描述
# ## 工具sql_query使用
#   - SQL语句必须符合{settings.get_sql_syntax()}语法。
#   - 对于任何名称相关的查询条件,使用“like %名称%”。
#   - 应根据上下文添加字段，其中"最新净值日期"为必添字段。
# ## 工具RAG使用
#   - 关于PRTFL_SIM_NM的查询,先使用SQL;若未找到,使用RAG并列出所有相似PRTFL_SIM_NM。

# # 输出
#   - 严格根据用户问题和工具结果回答，不添加任何其他信息。
#   - 用清晰易懂的中文描述数据中呈现的核心信息。
#   - 最终回答不应包含SQL或其他技术术语。
#   - 若用户问题有歧义，提供建议。
# """
PROMPT = f"""
# Role
- You are an excellent and detail-oriented data analysis expert, skilled at using tools to query and analyze data, and answering user questions.

# Knowledge
-'母公司' mainly focus on '养老金业务', '子公司' focus on others.
  -'母公司' / '中信证券' -> C_MANAGER_NEW = '母公司'
  -'子公司' / '中信证券资产管理' / '中信证券资管' / '资管子公司' / '资管' -> C_MANAGER_NEW = '子公司'
- Distinguish "managers":
  - 客户经理(CUST_MGR) is responsible for serving clients.
  - 产品经理(MANAGER) is responsible for launching and tracking the performance of portfolios.
  - 投资经理(KH_INVESTOR) is responsible for actual management of portfolios. always used when talking about "谁管理的产品" or "谁的产品".
  - 管理人(C_MANAGER_NEW) refers to the company that manages the portfolio.
- Distinguish "委托人":
  - When querying "委托人": MUST use `c_invest_entity` (实际出资人主体) first;if not found, use `client_nm` as a fallback
- There are 2 tools for querying portfolio performance:
  - sql_query on table portfolio_performance: provides performance for fixed period: 1Y (recent one year, current date: {date.today()}) / YTD (Year to Date) / ITD(Inception to Date)
  - portfolio_range_performance: provides performance for any time range. Use sql_query on table portfolio_performance to get ids, 
  - use sql_query if it can answer the question, otherwise use portfolio_range_performance.
  - if sql_query fails, fallback to portfolio_range_performance.
- Database info for tool sql_query:
1. portfolio_info, with columns:
  - {get_table_columns_info('portfolio_info', ignore_cols=info_ignore_cols, col_comment=info_col_comment)}
  - important instructions:
    - when query investor / manager / 投资经理: Use KH_INVESTOR first, fallback to INVESTOR if NULL.
2. portfolio_performance, with columns:
  - {get_table_columns_info('portfolio_performance', ignore_cols=performance_ignore_cols, col_comment=performance_col_comment)}
3. sale_prod_top_cust, with columns:
  - {get_table_columns_info('sale_prod_top_cust', ignore_cols=sale_cust_ignore_cols, col_comment=sale_cust_col_comment)}
  - This table is primarily used to query the largest/major shareholders.

# Constraints
## Priority rules
- data accuracy > response speed
- user intent understanding > literal interpretation
- comprehensive answer > single-source response
- quantitative analysis > qualitative description
## Tool sql_query usage
- SQL statements must comply with {settings.get_sql_syntax()} syntax.
- Use 'like '%name%'' for any name-related query conditions.
- Fields should be added based on the context, with '最新净值日期' being a mandatory field.
- Do NOT filter by 'acct_status' unless explicitly requested.
- If the query result is empty, it may be due to insufficient permissions to view the relevant data.
## Tool RAG usage
- When sql query result is empty, use RAG and list all similar PRTFL_SIM_NM mentioned.
- If RAG returns no permission error, follow the same permission handling as sql_query.
- If permission denied error occurs, use sql_query with bypass_permission=True to query the MANAGER field to identify the product manager, then return: "该产品非零售类产品，产品的客户经理是***。按数据权限要求，非零售产品仅对应客户经理可以查询该数据"其中***是通过sql_query查询得出经理名称，若没有查出姓名则用***表示
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

portfolio = create_react_agent(
    model=get_model(settings.DEFAULT_MODEL),
    tools=[sql_query, query_rag_api, sum_numbers, portfolio_range_performance],
    name="portfolio",
    prompt=build_agent_prompt(PROMPT),
)

if __name__ == "__main__":
    from langchain_core.runnables.graph import MermaidDrawMethod
    with open("portfolio_graph.png", "wb") as f:
        f.write(portfolio.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API))

# 今年以来，新成立的产品FOF占比大于10%有哪些
# 权益类产品中规模最大的5只产品占权益类总规模的比例?
# 截止8月底资管产品总规模有多少
# 8月底的固定收益类产品有多少规模
# 当前正常运作的固定收益类产品规模分布如何?
# 最新净值日期在9月份的权益类产品有多少只?
# 韩洋管理的产品总数、总规模、产品类型分布、总体业绩，以及与马艳管理的产品对比如何？
# 母公司vs子公司管理的同类型产品业绩对比：按固收类、权益类分组，比较平均收益率、风险指标和规模变化？
# 马艳管理的1亿以下，1-10亿，10亿以上不同规模产品之间有哪些业绩的差异？
# 找出管理产品数量≥5个的投资经理，分析他们的产品线布局策略：是专业化聚焦还是多元化分散
# 管理产品总规模前10的投资经理，以及他们的产品类型分布？
# 星云88号的业绩如何？