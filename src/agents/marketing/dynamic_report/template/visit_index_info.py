from .base import TemplateModule
from agents.tools.sql_query import sql_query
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core import get_model, settings

class VisitIndexInfoTemplate(TemplateModule):


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
                # 如果无法解析为JSON，直接返回无记录
                return {
                    "prompt": """
# 拜访周报详情
## 客户拜访详细分析
期间暂无记录
"""
                }
                
        # 如果data已经是列表，直接使用
        elif isinstance(data, list):
            processed_data = data
        
        # 处理列表数据
        if processed_data:
            # 构建客户拜访记录的格式化文本
            visit_records = []
            
            for index, record in enumerate(processed_data):
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
                    
                    # 格式化单条拜访记录
                    visit_record = f"""### 第{index+1}条拜访记录
日期：{create_date}
客户经理：{cust_manager}
客户信息：{marketing_project}
拜访内容：{visit_content}
后续计划：{plan}
获取信息：{information}
"""
                    visit_records.append(visit_record)
            
            # 为每条记录生成独立的模板内容
            record_prompts = []
            
            for index, record in enumerate(processed_data):
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
                    
                    # 为单条记录生成固定格式的模板内容
                    record_prompt = f"""
--- 第{index+1}条拜访记录分析 ---

你是一个专业的销售分析顾问，请基于以下客户拜访记录，生成详细的分析报告：

客户拜访记录：
日期：{create_date}
客户经理：{cust_manager}
客户信息：{marketing_project}
拜访内容：{visit_content}
后续计划：{plan}
获取信息：{information}

请按照以下结构生成分析：
1. 客户情况总结：描述客户的基本情况、当前合作状态等
2. 拜访成果分析：分析本次拜访的主要成果和获取的关键信息
3. 合作机会识别：基于拜访内容，识别潜在的合作机会
4. 后续行动建议：提出针对性的后续跟进建议

要求：
- 分析要深入具体，基于提供的信息
- 建议要实用可行，具有针对性
- 语言要专业简洁，避免冗余
- 所有结论必须基于提供的拜访记录
--- 分析结束 ---
"""
                    record_prompts.append(record_prompt)
                    # 打印record_prompts变量
                    print("record_prompts:", record_prompts)
            
            # 构建完整的提示词模板，包含所有记录的分析请求
            prompt = f"""
# 拜访周报详情

以下是需要分析的客户拜访记录：

{''.join(record_prompts)}

请为每条记录分别生成分析报告，并最终提供一个整体总结。
"""
            # 打印prompt变量
            print("prompt:", prompt)
        else:
            prompt = f"""
# 拜访周报详情
## 客户拜访详细分析
期间暂无记录
"""
            # 打印prompt变量
            print("prompt:", prompt)
        
        return {"prompt": prompt}