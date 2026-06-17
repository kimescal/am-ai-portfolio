from .base import TemplateModule
from agents.tools.sql_query import sql_query
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core import get_model, settings

class VisitIndexTemplate(TemplateModule):


    def fetch_data(self, args: dict) -> dict:
        begin_date = args.get('begin_date', '')
        end_date = args.get('end_date', '')

        QUERY_VISIT_INDEX_DATA = f"""
        SELECT DATE_FORMAT(create_date, '%m-%d') as create_date, cust_manager, customer_group, region, cust_name, visit_content,plan,information
        FROM sale_cust_dynamic_record
        WHERE create_date >= '{begin_date}'
        AND create_date <= '{end_date}'
                    """
        result = sql_query.invoke({"query": QUERY_VISIT_INDEX_DATA})
        return result

    def get_template_chunk(self, data: dict) -> dict[str, str]:
        # 处理数据，提取拜访记录
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
            # 准备LLM进行摘要生成
            model = get_model(settings.DEFAULT_MODEL)
            
            # 创建摘要prompt
            summary_prompt = PromptTemplate(
                template="请将以下文本总结为12字左右的中文摘要：\n\n{text}",
                input_variables=["text"]
            )
            
            # 创建摘要链
            summary_chain = summary_prompt | model | StrOutputParser()
            
            records = []
            # 表头
            records.append("日期 | 客户经理名 | 营销项目名 | 获取信息AI摘要")
            records.append("-" * 60)  # 分隔线
            
            for record in processed_data:
                if isinstance(record, dict):
                    # 提取记录中的关键字段
                    create_date = record.get('create_date', '未知日期')
                    cust_manager = record.get('cust_manager', '未知经理')
                    customer_group = record.get('customer_group', '')
                    region = record.get('region', '')
                    cust_name = record.get('cust_name', '')
                    visit_content = record.get('visit_content', '')
                    plan = record.get('plan', '')
                    information = record.get('information', '')
                    
                    # 拼接营销项目名
                    marketing_project = f"{customer_group}-{region}-{cust_name}"
                    
                    # 合并三个字段的内容用于生成摘要
                    combined_content = f"{visit_content} {plan or ''} {information or ''}"
                    
                    # 生成AI摘要
                    try:
                        ai_summary = summary_chain.invoke({"text": combined_content})
                    except Exception as e:
                        # 如果摘要生成失败，使用默认值
                        ai_summary = "摘要生成失败"
                    
                    # 构建表格行
                    record_str = f"{create_date} | {cust_manager} | {marketing_project} | {ai_summary}"
                    records.append(record_str)
            
            if len(records) > 2:  # 检查是否有数据行
                dynamic_data = "\n".join(records)
            else:
                dynamic_data = "期间暂无记录"
        elif not dynamic_data:  # 如果是无法解析的字符串，dynamic_data已设置
            dynamic_data = "期间暂无记录"
        
        # 将处理后的数据应用到模板中
        template = {
            "prompt": """
你是一个专业的工作报告撰写助手。请根据以下拜访记录，生成一份拜访索引报告。

拜访记录：
{dynamic_data}

请按照以下结构生成报告：
# 拜访情况索引
## 拜访记录索引表
{dynamic_data}

要求：
- 直接展示表格内容，不需要额外的文字描述
- 保持表格格式清晰
- 所有数据只能来源于拜访记录，实事求是
- 若没有记录，直接写"期间暂无记录"
""".format(dynamic_data=dynamic_data)
        }
        return template