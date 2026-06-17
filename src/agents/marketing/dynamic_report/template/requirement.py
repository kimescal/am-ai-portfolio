from langchain_core.runnables import RunnableConfig

from .base import TemplateModule
from agents.tools.sql_query import sql_query


class CompanyRequirementTemplate(TemplateModule):

    title_name = "需求报告总结"

    def fetch_data(self, args: dict) -> dict:
        begin_date = args.get('begin_date', '')
        end_date = args.get('end_date', '')
        
        QUERY_REQUIREMENT_DATA = f"""
        select cust_name,extend_requirement,cust_manager_team,cust_fund_source from sale_cust_invest_requirement
        WHERE create_time >= '{begin_date}'
        AND create_time <= '{end_date}'
                    """
        
        result = sql_query.invoke({"query": QUERY_REQUIREMENT_DATA})
        return result

    def get_template_chunk(self, data: dict,config:RunnableConfig) -> dict[str, str]:
        # 处理数据，提取需求记录
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
            # 统计和分析数据
            requirement_count = len(processed_data)
            
            records.append(f"需求总量: {requirement_count}")
            
            for record in processed_data:
                if isinstance(record, dict):
                    customer_name = record.get('cust_name', '未知客户')
                    extend_requirement = record.get('extend_requirement', '无详细需求')
                    cust_manager_team = record.get('cust_manager_team', '未知团队')
                    cust_fund_source = record.get('cust_fund_source', '未指定资金来源')
                    
                    records.append(f"\n---")
                    records.append(f"客户: {customer_name}")
                    records.append(f"负责团队: {cust_manager_team}")
                    records.append(f"资金来源: {cust_fund_source}")
                    records.append(f"需求详情: {extend_requirement}")
            
            if records:
                dynamic_data = "\n".join(records)
            else:
                dynamic_data = "期间暂无需求记录"
        elif not dynamic_data:  # 如果是无法解析的字符串，dynamic_data已设置
            dynamic_data = "期间暂无需求记录"
        
        # 将处理后的数据应用到模板中
        template = {
            "prompt": """
你是一名专业的工作报告撰写助手。请根据以下客户需求记录，生成一份需求分析报告。

需求记录(格式：{{客户名称：需求内容}})：
{dynamic_data}

请按照以下结构生成报告：
# 需求情况总结
## 战略客户亮点进展、风险与挑战
- 分析战略客户的亮点进展，基于客户资金来源判断战略客户类型
- 基于客户名称和需求内容推断潜在风险与挑战
- 若相关数据为空，请直接写"期间暂无记录"
## 区域客户亮点进展、风险与挑战
- 分析区域客户的亮点进展，基于客户管理团队判断区域客户类型
- 基于客户名称和需求内容推断潜在风险与挑战
- 若相关数据为空，请直接写"期间暂无记录"
## 业务观察、学习与思考
## 市场与策略洞察
- 若相关数据为空，请直接写"期间暂无记录"
## 展业方向与计划
- 若相关数据为空，请直接写"期间暂无记录"

要求：
- 不用生成报告标题
- 若没有记录，直接写"期间暂无需求记录",单要保留报告结构
- 条理清晰，语言简洁专业
- 所有数据只能来源于需求记录，实事求是
""".format(dynamic_data=dynamic_data)
        }
        return template