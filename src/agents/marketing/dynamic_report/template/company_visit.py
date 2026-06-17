from langchain_core.runnables import RunnableConfig

from .base import TemplateModule
from agents.tools.sql_query import sql_query


class CompanyVisitTemplate(TemplateModule):

    title_name = "公司拜访记录"

    def fetch_data(self, args: dict) -> dict:
        begin_date = args.get('begin_date', '')
        end_date = args.get('end_date', '')

        QUERY_COMPANY_DATA = f"""
        SELECT  data_date, cust_name, dept_name, first_strategy, visit_content, extra_ctcontent, cust_manager, creater, updater, plan, information, region, customer_group
        FROM sale_cust_dynamic_record
        WHERE data_date >= '{begin_date}'
        AND data_date <= '{end_date}'
                    """
        
        result = sql_query.invoke({"query": QUERY_COMPANY_DATA})
        return result

    def get_template_chunk(self, data: dict,config:RunnableConfig) -> dict[str, str]:
        # 处理数据，提取公司拜访记录
        dynamic_data = ""
        
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
            # 按区域分组整理数据，因为SQL查询中没有team_id字段
            region_records = {}
            
            for record in processed_data:
                if isinstance(record, dict):
                    # 提取所有可用的字段
                    region = record.get('region', '未知区域')
                    customer_group = record.get('customer_group', '未知客户群体')
                    manager_name = record.get('cust_manager', '未知经理')
                    customer_name = record.get('cust_name', '未知客户')
                    dept_name = record.get('dept_name', '未知客户部门名称')
                    first_strategy = record.get('first_strategy', '未知一级策略')
                    visit_content = record.get('visit_content', '未知拜访内容')
                    extra_ctcontent = record.get('extra_ctcontent', '未知提炼分享内容')
                    visit_date = record.get('data_date', '未知日期')
                    
                    # 组合客户信息
                    customer_info = f"{customer_name}"
                    if dept_name:
                        customer_info += f"({dept_name})"
                    
                    # 构建拜访详情
                    visit_detail = f"{visit_date} - {manager_name}拜访{customer_info}: {visit_content}"
                    if first_strategy:
                        visit_detail += f" [策略: {first_strategy}]"
                    if extra_ctcontent:
                        visit_detail += f" [要点: {extra_ctcontent}]"
                    
                    # 按区域分组
                    if region not in region_records:
                        region_records[region] = []
                    region_records[region].append((customer_group, visit_detail))
            
            # 格式化输出，按区域和客户群体组织
            for region, region_data in region_records.items():
                records.append(f"\n=== 区域: {region} ===")
                
                # 进一步按客户群体分组
                group_records = {}
                for customer_group, visit_detail in region_data:
                    if customer_group not in group_records:
                        group_records[customer_group] = []
                    group_records[customer_group].append(visit_detail)
                
                for group, group_data in group_records.items():
                    records.append(f"\n--- 客户群体: {group} ---")
                    for visit_detail in group_data:
                        records.append(visit_detail)
            
            if records:
                dynamic_data = "\n".join(records)
            else:
                dynamic_data = "期间暂无记录"
        elif not dynamic_data:  # 如果是无法解析的字符串，dynamic_data已设置
            dynamic_data = "期间暂无记录"
        
        # 将处理后的数据应用到模板中
        template = {
            "prompt": """
你是一个专业的公司级工作报告撰写助手。请根据以下拜访记录，生成一份公司级客户拜访报告。

拜访记录：
{dynamic_data}


请按照以下结构生成报告：
# 拜访情况总结
## 公司整体工作概述
- 全面总结公司客户拜访情况，突出战略级成果和进展
## 各团队工作亮点
- 若团队无记录则直接写“期间暂无记录”
## 公司级重要成果与进展
## 公司运营中存在的问题与挑战

要求：
- 不用生成报告标题
- 条理清晰，语言简洁专业
- 所有数据只能来源于拜访记录，实事求是
- 若团队没有记录，直接写“期间暂无记录”
- 不生成报告大标题
""".format(dynamic_data=dynamic_data)
        }
        return template