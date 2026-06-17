from langchain_core.runnables import RunnableConfig

from .base import TemplateModule
from agents.tools.sql_query import sql_query


class EmployeeVisitTemplate(TemplateModule):

    title_name = "个人拜访记录"

    def fetch_data(self, args: dict) -> dict:
        begin_date = args.get('begin_date', '')
        end_date = args.get('end_date', '')
        employee_name = next(iter(args.get("employees").keys()))

        QUERY_EMPLOYEE_DATA = f"""
        SELECT data_date, cust_name, dept_name, first_strategy, visit_content, extra_ctcontent, cust_manager, creater, updater, plan, information, region, customer_group
        FROM sale_cust_dynamic_record
        WHERE (cust_manager LIKE '{{name}}'
                OR cust_manager LIKE '{{name}},%'
                OR cust_manager LIKE '%,{{name}}'
                OR cust_manager LIKE '%,{{name}},%')
        AND data_date >= '{begin_date}'
        AND data_date <= '{end_date}'
                    """

        result = sql_query.invoke({"query": QUERY_EMPLOYEE_DATA.format(name=employee_name)})
        return result

    def get_template_chunk(self, data: dict,config:RunnableConfig) -> dict[str, str]:
        # 处理数据，提取拜访记录
        dynamic_data = ""
        employees = next(iter(config.get("configurable").get("employees") or {}),"")

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
                    visit_content = record.get('visit_content', '无内容')
                    visit_date = record.get('data_date', '未知日期')
                    dept_name = record.get('dept_name', '未知部门')
                    first_strategy = record.get('first_strategy', '无策略')
                    extra_ctcontent = record.get('extra_ctcontent', '')
                    region = record.get('region', '未知区域')
                    plan = record.get('plan', '未知计划')
                    information = record.get('information', '未知详情')
                    customer_group = record.get('customer_group', '未知客户群')
                    
                    # 构建更详细的记录信息
                    record_str = f"{visit_date} - {dept_name}拜访{customer_name}({customer_group}/{region})\n"
                    record_str += f"  策略: {first_strategy}\n"
                    record_str += f"  计划: {plan}\n"
                    record_str += f"  详情: {information}\n"
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
你是一名专业的工作报告撰写助手。请根据以下拜访记录，生成一份客户拜访报告。

拜访记录(格式：{{客户经理姓名：拜访记录}})：
{dynamic_data}

请按照以下结构生成报告：
# {employees}拜访情况总结
## 工作总结
### 核心业务进展
- 突出工作重点，成果和下一步计划
### 客户覆盖与跟进
### 内部协同事项
### 其他工作事项
## 业务观察、学习与思考
### 市场与策略洞察
### 展业方向与计划

要求：
- 不用生成报告标题
- 若没有记录，保留一级标题，第二行开始直接写“期间暂无记录”
- 条理清晰，语言简洁专业
- 所有数据只能来源于拜访记录，实事求是
""".format(dynamic_data=dynamic_data,employees=employees)
        }
        return template
