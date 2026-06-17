from langchain_core.runnables import RunnableConfig
from datetime import datetime

from .base import TemplateModule
from agents.tools.sql_query import sql_query


class EmployeeNorthVisitTemplate(TemplateModule):

    title_name = "华北个人拜访记录"

    def fetch_data(self, args: dict) -> dict:
        begin_date = args.get('begin_date', '')
        end_date = args.get('end_date', '')
        employee_name = next(iter(args.get("employees").keys()))

        QUERY_EMPLOYEE_DATA = f"""
        SELECT data_date, cust_name, dept_name, first_strategy, visit_content, extra_ctcontent, cust_manager, creater, updater, plan, information, region, customer_group
        ,dynamic_type,channel,area_coordinate_flag
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

        area_coordinate_records = []  # 存储区域协同记录
        other_coordinate_records = []  # 存储其他协同记录

        # 处理列表数据
        if processed_data:
            records = []
            for record in processed_data:
                if isinstance(record, dict):
                    # 提取记录中的关键字段
                    customer_name = record.get('cust_name', '未知客户')
                    visit_content = record.get('visit_content', '无内容')
                    visit_date = record.get('data_date', '未知日期')
                    # 转换日期格式：2026-04-22T00:00:00.000 -> 2026年04月22日
                    if visit_date and visit_date != '未知日期':
                        try:
                            # 处理多种日期格式
                            if 'T' in visit_date:
                                dt = datetime.fromisoformat(visit_date.replace('T', ' ').split('.')[0])
                            else:
                                dt = datetime.strptime(visit_date.split(' ')[0], '%Y-%m-%d')
                            visit_date = f"{dt.year}年{dt.month:02d}月{dt.day:02d}日"
                        except Exception:
                            # 如果转换失败，保留原始日期格式
                            pass
                    dept_name = record.get('dept_name', '未知部门')
                    first_strategy = record.get('first_strategy', '无策略')
                    extra_ctcontent = record.get('extra_ctcontent', '')
                    region = record.get('region', '未知区域')
                    plan = record.get('plan', '未知计划')
                    information = record.get('information', '未知详情')
                    customer_group = record.get('customer_group', '未知客户群')
                    dynamic_type = record.get('dynamic_type', '拜访类型')
                    channel = record.get('channel', '拜访渠道')
                    area_coordinate_flag = record.get('area_coordinate_flag', '是否区群协同')
                    
                    # 检查是否为区域协同记录 (dynamic_type='1' 且 channel='中信证券')
                    is_area_coordinate = (dynamic_type == '1' and channel == '中信证券')
                    if is_area_coordinate:
                        # 格式：x年x月x日拜访xxx营业部
                        area_record = f"{visit_date}拜访{customer_name}"
                        area_coordinate_records.append(area_record)
                    
                    # 检查是否为其他协同记录 (area_coordinate_flag='是')
                    if area_coordinate_flag == '是':
                        other_record = f"{visit_date}拜访{customer_name}"
                        other_coordinate_records.append(other_record)
                    
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
        
        # 构建区域协同内容
        if area_coordinate_records:
            area_coordinate_content = "\n".join(f"- {record}" for record in area_coordinate_records)
        else:
            area_coordinate_content = "暂无记录"
        
        # 构建其他协同内容
        if other_coordinate_records:
            other_coordinate_content = "\n".join(f"- {record}" for record in other_coordinate_records)
        else:
            other_coordinate_content = "暂无记录"
        
        # 将处理后的数据应用到模板中
        template = {
            "prompt": """
你是一名专业的工作报告撰写助手。请根据以下拜访记录，生成一份客户拜访报告。

拜访记录(格式：{{客户经理姓名：拜访记录}})：
{dynamic_data}

请按照以下结构生成报告：
# {employees}上周工作简报及业务观察

## 一、主要工作进展
### 1）新增规模及落地账户
-
-
-

### 2）各类客群覆盖情况及重点项目进展情况
#### -银行客群：

#### -企业客群：

#### -财富客群：

#### -跨境客群：


### 3）区域协同
{area_coordinate_content}

### 4）其他协同
{other_coordinate_content}

### 5）近期业务方向


## 二、市场动态观察与业务思考

要求：
- 条理清晰，语言简洁专业
- 所有数据只能来源于拜访记录，实事求是
- 若某部分没有相关记录，保留标题，内容写“暂无记录”
""".format(dynamic_data=dynamic_data, employees=employees, area_coordinate_content=area_coordinate_content, other_coordinate_content=other_coordinate_content)
        }
        return template