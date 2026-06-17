from langchain_core.runnables import RunnableConfig

from .base import TemplateModule
from agents.tools.sql_query import sql_query
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../')))

# 导入配置模块
from jobs.dynamic_report_job.config import get_employees_by_team


class TeamVisitTemplate(TemplateModule):

    title_name = "团队拜访记录"

    def fetch_data(self, args: dict) -> dict:
        begin_date = args.get('begin_date', '')
        end_date = args.get('end_date', '')
        team_name = args.get('team_name', '')
        field_name = args.get('field_name', 'cust_manager')  # 默认使用cust_manager字段
        
        # 构建基础SQL查询
        QUERY_TEAM_DATA = f"""
        SELECT data_date, cust_name, dept_name, first_strategy, visit_content, extra_ctcontent, cust_manager, creater, updater, plan, information, region, customer_group
        FROM sale_cust_dynamic_record
        where data_date >= '{begin_date}'
        AND data_date <= '{end_date}'
        """
        
        # 获取团队成员列表并构建正则匹配条件
        if team_name:
            team_members = get_employees_by_team(team_name)
            if team_members:
                # 构建正则匹配条件
                member_names = list(team_members.keys())
                if member_names:
                    # 构建单个正则表达式，将所有成员名用|分隔
                    member_names_str = "|".join(member_names)
                    # 构建完整的正则条件：(^|,)(成员1|成员2|...)(,|$)
                    QUERY_TEAM_DATA += f" AND {field_name} REGEXP '(^|,)({member_names_str})(,|$)'"
        
        result = sql_query.invoke({"query": QUERY_TEAM_DATA})
        return result

    def get_template_chunk(self, data: dict,config:RunnableConfig) -> dict[str, str]:
        # 处理数据，提取团队拜访记录
        dynamic_data = ""
        team_name = config.get("configurable").get("team_name")
        # 处理可能的JSON字符串数据
        processed_data = []
        
        # 检查data是否为字符串，尝试解析为JSON
        if isinstance(data, str):
            try:
                import json
                parsed_data = json.loads(data)
                if isinstance(parsed_data, list):
                    processed_data = parsed_data
            except (json.JSONDecodeError, TypeError):
                # 如果无法解析为JSON，将其视为普通字符串
                dynamic_data = data
                
        # 如果data已经是列表，直接使用
        elif isinstance(data, list):
            processed_data = data
        
        # 处理列表数据
        if processed_data:
            records = []
            for record in processed_data:
                if isinstance(record, dict):
                    # 提取记录中的关键字段
                    customer_name = record.get('cust_name', '未知客户')
                    manager_name = record.get('cust_manager', '未知经理')
                    visit_content = record.get('visit_content', '无内容')
                    visit_date = record.get('data_date', '未知日期')
                    dept_name = record.get('dept_name', '未知部门')
                    first_strategy = record.get('first_strategy', '无策略')
                    extra_ctcontent = record.get('extra_ctcontent', '')
                    region = record.get('region', '未知区域')
                    customer_group = record.get('customer_group', '未知客户群')
                    
                    # 构建更详细的记录信息
                    record_str = f"{visit_date} - {dept_name}-{manager_name}拜访{customer_name}({customer_group}/{region})\n"
                    record_str += f"  策略: {first_strategy}\n"
                    record_str += f"  内容: {visit_content}"
                    if extra_ctcontent:
                        record_str += f"\n  补充: {extra_ctcontent}"
                    records.append(record_str)
            
            if records:
                dynamic_data = "\n\n".join(records)
            else:
                dynamic_data = "期间暂无记录"
        elif not dynamic_data:  # 如果是无法解析的字符串，dynamic_data已设置
            dynamic_data = "期间暂无记录"
        
        # 将处理后的数据应用到模板中
        template = {
            "prompt": """
你是一个专业的工作报告撰写助手。请根据以下拜访记录，生成一份团队客户拜访报告。

拜访记录(格式：{{客户经理姓名：拜访记录}})：
{dynamic_data}

请按照以下结构生成报告：
# {team_name}团队拜访情况总结
## 团队工作概述
- 全面总结团队工作情况，突出团队合作和成果
## 各成员工作亮点
- 若成员无记录则直接写“期间暂无记录”
## 团队存在的问题与挑战
## 团队下一步工作计划

要求：
- 不用生成报告标题
- 条理清晰，语言简洁专业
- 所有数据只能来源于拜访记录，实事求是
- 不生成报告大标题
""".format(dynamic_data=dynamic_data, team_name=team_name)
        }
        return template