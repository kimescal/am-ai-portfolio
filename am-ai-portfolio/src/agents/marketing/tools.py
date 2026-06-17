import logging
import json
import requests
import os
from datetime import datetime, timedelta
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from core.settings import settings
from core.llm import get_model
from typing import List, Dict, Any, Optional
from agents.marketing.dynamic_report.template import TEMPLATE_REGISTRY
from agents.marketing.dynamic_report.report import report_generator
from agents.tools.sql_permission import permission_checker
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


@tool
def portfolio_range_performance(
    portfolio_id_list: List[str],
    start_dt: str,
    end_dt: str,
) -> str:
    """
    Obtain portfolio performance information. Support batch queries for multiple products.
    WARNING: Pass aLL protfolio IDs and names found by sql_query as a list; do NOT omit any.
    Args:
    - portfolio_id_list(List[str]): portfolio id list.
    - start_dt(str, format: YYYY-MM-DD): range start date.
    - end_dt(str, format: YYYY-MM-DD): range end date.
    Returns:
    - str: performance data, json format.
    """
    # 从settings获取AMCELL服务地址
    amcell_addr = settings.AMCELL_ADDR

    try:
        payload = {
            'portfolio_id_list': portfolio_id_list,
            'start_dt': start_dt,
            'end_dt': end_dt,
        }
        # 确保URL格式正确，只使用基础地址，路径部分明确指定
        base_url = amcell_addr.rstrip('/')
        response = requests.post(
            f'{base_url}/api/v1/portfolio/performance',
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        raise TimeoutError('请求超时, 请稍后重试')
    except requests.exceptions.RequestException as e:
        raise requests.exceptions.RequestException(f'请求失败: {str(e)}')
    except ValueError as e:
        raise ValueError(f'解析响应数据失败: {str(e)}')

@tool
async def generate_weekly_visit_report(
    report_level: str = "employee",
    employee_name: Optional[str] = None,
    team_name: Optional[str] = None,
    data_days: int = 7,
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    生成详细的拜访周报文档。仅在用户明确要求生成"周报"时使用。
    注意：如果用户只是询问简单的统计数据（如"拜访了多少次"、"有哪些客户"），请直接使用 SQL 查询工具，不要调用此工具。
    Args:
        report_level: 报告级别。
          - "employee": 个人周报（筛选 `cust_manager`）
          - "team": 团队周报(查询某个团队，如"华南区域"、"银行客群"等）
          - "company": 全公司周报(仅当用户明确说"全公司"或"公司级别"时使用）
        employee_name: 员工姓名（当 report_level="employee" 时必填，对应表中的 `cust_manager`）
        team_name: 团队名称（当 report_level="team" 时必填）
        data_days: 统计天数,默认7天（当未指定 begin_date 时使用）
        begin_date: 开始日期，格式 YYYY-MM-DD（可选，用于查询任意时间段）
        end_date: 结束日期，格式 YYYY-MM-DD（可选，默认为今天）
        config: RunnableConfig，包含用户身份信息
    Returns:
        str: 生成的周报内容
    """
    
    try:
        user_id = config.get("configurable", {}).get("user_id") if config else None
        if not user_id:
            return "无法生成周报：未获取到用户身份信息，请重新登录。"

        user_name = permission_checker.get_employee_name(user_id)
        if not user_name:
            return f"无法生成周报：未找到工号 {user_id} 对应的员工信息。"
        
        logger.info(f"[周报权限] user_id={user_id}, user_name={user_name}, report_level={report_level}, team_name={team_name}")
        
        # 复用 jobs/dynamic_report_jobs/config.py 中的配置读取逻辑
        import jobs.dynamic_report_job.config as cfg
        
        company_leaders = cfg.get_company_leaders()
        teams = cfg.get_teams()

        is_company_leader = user_name in company_leaders or user_id in company_leaders.values()
        admins = cfg.get_admins()
        is_admin = user_name in admins or user_id in admins.values()
        has_full_access = is_company_leader or is_admin  # 领导和管理员权限相同
        
        # 查找用户是否是某个团队的负责人
        user_team_as_leader = next(
            (t_name for t_name, info in teams.items() 
             if user_name in info.get("leader", {}) or user_id in info.get("leader", {}).values()),
            None
        )
        
        # 辅助函数：模糊匹配团队名
        def match_team(name):
            if not name:
                return None
            return next((t for t in teams.keys() if t == name or t.startswith(name) or name in t), None)
        
        if report_level == "employee":
            if not employee_name:
                employee_name = user_name
            elif employee_name != user_name and not has_full_access:
                # 团队负责人只能查本团队成员
                team_members = {**cfg.get_employees_by_team(user_team_as_leader), **(cfg.get_team_leader(user_team_as_leader) or {})} if user_team_as_leader else {}
                if employee_name not in team_members:
                    return f"您没有权限查看 {employee_name} 的拜访周报。只能查看自己或本团队成员的周报，或联系管理员获取权限。。"

        elif report_level == "team":
            team_name = match_team(team_name) or team_name  # 模糊匹配
            if not has_full_access:
                if not team_name:
                    team_name = user_team_as_leader or None
                if not team_name:
                    return "您不是任何团队的负责人，请指定团队名称或联系管理员获取权限，或联系管理员获取权限。。"
                if team_name != user_team_as_leader:
                    return f"您不是团队「{team_name}」的负责人，无法生成该团队周报，或联系管理员获取权限。。"

        elif report_level == "company":
            if not has_full_access:
                return "您没有权限生成公司周报。只有公司领导或管理员可以生成公司周报，或联系管理员获取权限。"

        # 构建配置，复用 run.py 的模式
        configurable = {
            "template": [f"{report_level}_visit"],
            "data_days": data_days,
            "employees": cfg.get_employees_by_team(team_name) if report_level == 'team' else ({employee_name: {}} if employee_name else {}),
            "team_name": team_name,
            "team_leader": cfg.get_team_leader(team_name) if report_level == 'team' else None,
        }
        
        # 只在有实际日期值时才传递，否则让 report.py 根据 data_days 计算
        if begin_date:
            configurable["begin_date"] = begin_date
        if end_date:
            configurable["end_date"] = end_date
            
        report_config = {"configurable": configurable}
        
        result = await report_generator.ainvoke({}, report_config)
        
        # 返回生成的报告内容
        return result.get("final_report", "生成报告失败")
        
    except Exception as e:
        logger.error(f"Error generating weekly report: {e}", exc_info=True)
        return f"生成周报时出错: {str(e)}"


if __name__ == "__main__":
    from tools.rag_api import sql_query

    # Simple query example
    sql = "SELECT * FROM sale_cust_invest_requirement limit 10"
    print(f"Executing SQL: {sql}")
    result = sql_query.invoke(sql)
    print(f"Result: {result[:500]}...")