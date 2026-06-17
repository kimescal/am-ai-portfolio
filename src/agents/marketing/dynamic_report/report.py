import asyncio
import json
import logging
import os
import traceback

import requests
from datetime import datetime, timedelta
from typing import Dict, TypedDict, Any
import base64
from markdown_pdf import MarkdownPdf, Section


from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from cachetools import TTLCache

from core import get_model, settings
from service.qiwei.zhiyu_platform import uploadFile, sendFile, get_api_token_cached, push_wechat_text
from agents.tools.sql_query import sql_query

import logging
from .template import TEMPLATE_REGISTRY
from typing import Annotated, List, TypedDict, Any
import operator
from langgraph.constants import Send


logger = logging.getLogger(__name__)


token_cache = TTLCache(maxsize=1, ttl=43200)  # 12hours

def truncate_string_by_utf8_bytes(text: str, max_bytes: int = 2000, title_name: str = "") -> List[str]:
    """
    将字符串按UTF-8字节长度截断为多个子字符串
    
    参数:
        text: 要截断的字符串
        max_bytes: 每个子字符串的最大字节数
        title_name: 标题名称，用于在切割后的片段前添加带序号的前缀
        
    返回:
        List[str]: 截断后的子字符串列表
    """
    if not text:
        return [""]
    
    # 先检查是否需要切割
    total_bytes = len(text.encode('utf-8'))
    
    # 如果不需要切割且有标题，直接返回原文本
    if total_bytes <= max_bytes:
        return [text]
    
    # 需要切割的情况
    result = []
    current_chunk = ""
    current_bytes = 0
    
    for char in text:
        # 获取当前字符的字节长度
        char_bytes = len(char.encode('utf-8'))
        
        # 如果添加当前字符会超过最大字节数
        if current_bytes + char_bytes > max_bytes:
            # 如果当前chunk为空，说明单个字符就超过了最大字节数，也需要添加
            if current_chunk:
                result.append(current_chunk)
            # 重置当前chunk
            current_chunk = char
            current_bytes = char_bytes
        else:
            # 添加字符到当前chunk
            current_chunk += char
            current_bytes += char_bytes
    
    # 添加最后一个chunk
    if current_chunk:
        result.append(current_chunk)
    
    # 如果有标题名称且需要切割，在每个片段前添加带序号的标题前缀
    if title_name and len(result) > 1:
        prefixed_result = []
        for i, part in enumerate(result, 1):
            prefix = f"{title_name} Part{i}"
            prefixed_result.append(f"{prefix}\n{part}")
        return prefixed_result
    
    return result

def get_api_token_cached() -> str:
    """Get API token with caching"""

    if 'token' in token_cache:
        logger.info("Using cached API token")
        return token_cache['token']

    try:
        data = {
            "userCode": settings.QIWEI_PUSH_API_LOGIN_USERCODE,
            "password": settings.QIWEI_PUSH_API_LOGIN_PASSWORD
        }

        response = requests.post(settings.QIWEI_PUSH_API_URL+"/login", json=data)
        if response.status_code == 200:
            result = response.json()
            token = result.get("data", {}).get("token", "")
            if token:
                token_cache['token'] = token
                logger.info("Successfully obtained and cached new API token")
                return token
            else:
                logger.error("No token found in API response")
                return ""
        else:
            logger.error(f"Failed to get token: HTTP {response.status_code}")
            return ""
    except Exception as e:
        logger.error(f"Error getting API token: {e}")
        return ""

class ManagerReportState(TypedDict):
    begin_date: str
    end_date: str
    template_data: Dict[str, Any]
    report_content: str
    error_message: str
    total_records: int
    report_config: dict
    prompt_context: str  # 拼接好的 Prompt
    sections: Annotated[List[dict], operator.add]
    final_report: str
    report_file_path: str

class TemplateNodeState(TypedDict):
    template_name: str
    data: Any
    order: int


def map_template(state: ManagerReportState, config: RunnableConfig):
    """
    根据配置和数据，分发任务给 generate_section 节点
    """
    configurable = config.get('configurable', {}) if config else {}
    raw_data = state.get("template_data", {})
    needed_templates = configurable.get("template", [])

    sends = []
    for idx, template_name in enumerate(needed_templates):
        if template_name in raw_data:
            payload = TemplateNodeState(
                template_name=template_name,
                data=raw_data[template_name],
                order=idx  # 记录原始顺序
            )
            # 发送到 "generate_section" 节点
            sends.append(Send("generate_template_node", payload))
    return sends

def generate_template_node(state: TemplateNodeState, config: RunnableConfig):
    """
    Worker Node: Responsible for generating only its specific section of the report.
    Adapted to work with the dictionary structure from collect_data_node.
    """
    mod_name = state["template_name"]
    order = state["order"]
    logger.info(f"""generate_section_node action: template_name={mod_name}""")

    # 从 state 中获取 template_data 字典
    template_data = state.get("data", {})


    content = ""
    if mod_name in TEMPLATE_REGISTRY:
        handler = TEMPLATE_REGISTRY[mod_name]

        template = handler.get_template_chunk(template_data,config)
        
        # 检查是否使用大模型生成内容
        use_llm = getattr(handler, 'use_llm', True)  # 默认使用大模型
        
        if use_llm:
            # 从返回的模板字典中提取 prompt
            prompt = template.get("prompt", "")
            model = get_model(settings.DEFAULT_MODEL)
            content = model.invoke([HumanMessage(content=prompt)])
        else:
            # 不使用大模型，直接返回模板数据，但保持与模型返回相同的格式（AIMessage）
            prompt_content = template.get("prompt", "")
            content = AIMessage(content=prompt_content)

    # 直接写死标题处理逻辑，不再依赖模板中的title_name属性
    if mod_name == "employee_visit":
        configurable = config.get('configurable', {}) if config else {}
        employees = configurable.get('employees', {})
        if employees:
            employee_name = next(iter(employees.keys()))
            title_name = f"#{employee_name}个人拜访记录"
        else:
            title_name = "#个人拜访记录"
    elif mod_name == "team_visit":
        configurable = config.get('configurable', {}) if config else {}
        team_name = configurable.get('team_name', '')
        if team_name:
            title_name = f"#{team_name}团队拜访记录"
        else:
            title_name = "#团队拜访记录"
    elif mod_name in ["company_visit", "company_requirement"]:
        # 公司级别的标题处理
        title_name = f"#公司拜访记录"
    else:
        # 默认标题
        title_name = "#报告"


    return {
        "sections": [{
            "order": order,
            "template_name": mod_name,
            "content": content,
            "title_name": title_name
        }]
    }


def compile_report_node(state: ManagerReportState):
    """
    Reducer Node: Aggregates all section fragments.
    """
    unordered_sections = state.get("sections", [])

    sorted_sections = sorted(unordered_sections, key=lambda x: x["order"])

    full_text_parts = "\n\n".join([item['content'].content for item in sorted_sections])



    return {"final_report": full_text_parts}

async def prepare_args_node(state: ManagerReportState, config: RunnableConfig) -> Dict:
    """
    Prepare arguments for report generation
    """
    try:
        configurable = config.get('configurable', {}) if config else {}
        logger.info(f"  → Configurable: {configurable}...")

        data_days = configurable.get('data_days', 7)
        end_date = datetime.now().strftime('%Y-%m-%d')
        begin_date = (datetime.now() - timedelta(days=data_days)).strftime('%Y-%m-%d')

        logger.info(f"  → Date range: {begin_date} ~ {end_date}")
        return { "begin_date": begin_date, "end_date": end_date }
    except Exception as e:
        logger.error(f"Error preparing arguments: {e}", exc_info=True)
        return { "error_message": f"Error preparing arguments: {e}" }

async def collect_data_node(state: ManagerReportState, config: RunnableConfig) -> Dict:
    """
    Collect data for report generation using async concurrent processing
    """
    try:
        configurable = config.get('configurable', {}) if config else {}
        needed_templates = configurable.get("template", [])
        begin_date = state.get('begin_date', '')
        end_date = state.get('end_date', '')

        logger.info(f"  → Collecting data concurrently for template: {', '.join(needed_templates)}")

        # 构建查询参数
        base_query_args = {
            'begin_date': begin_date,
            'end_date': end_date,
            **configurable  # 传递所有配置参数
        }

        # 创建异步获取数据的任务函数
        async def fetch_template_data(template_name):
            if template_name not in TEMPLATE_REGISTRY:
                logger.warning(f"    - Template {template_name} not found in registry")
                return (template_name, {"error": f"Template {template_name} not registered"})

            try:
                logger.info(f"    - Starting data collection for Template: {template_name}")
                handler_class = TEMPLATE_REGISTRY[template_name]

                # 如果fetch_data是同步方法，使用默认执行器执行
                if not hasattr(handler_class.fetch_data, '__await__'):
                    # 使用线程池执行同步操作
                    data = handler_class.fetch_data(base_query_args)
                else:
                    # 如果是异步方法，直接调用
                    data = await handler_class.fetch_data(base_query_args)

                logger.info(f"    - Template {template_name} data collected successfully")
                return (template_name, data)
            except Exception as e:
                logger.error(f"    - Error collecting data for Template {template_name}: {e}")
                return (template_name, {"error": str(e)})

        # 并发执行所有模块的数据收集任务
        tasks = [fetch_template_data(mod_name) for mod_name in needed_templates]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # 将结果转换为字典
        all_data = dict(results)

        logger.info(f"  → Data collection completed. Templates processed: {list(all_data.keys())}")
        return {"template_data": all_data}

    except Exception as e:
        logger.error(f"  ✗ Data collection failed: {e}", exc_info=True)
        return { "error_message": f"Data collection failed: {e}" }


async def write_report_node(state: ManagerReportState, config: RunnableConfig) -> Dict:
    """
    Write report content to file
    """
    try:
        configurable = config.get('configurable', {}) if config else {}
        report_level = configurable.get('report_level', 'employee')
        employees = configurable.get('employees', {})
        team_name = configurable.get('team_name', '')
        begin_date = state.get('begin_date', '')
        end_date = state.get('end_date', '')
        report_content = state.get('final_report', '')

        logger.info(f"  → Writing report to file")

        reports_dir = "reports/dynamic_report"
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)

        # Determine filename based on report level
        if report_level == "employee":
            employee_name = next(iter(employees.keys()))
            filename = f"资管公司客户拜访周报({employee_name}_{begin_date}~{end_date}).md"
        elif report_level == "team":
            filename = f"资管公司客户拜访周报({team_name}_{begin_date}~{end_date}).md"
        else:  # company
            filename = f"资管公司客户拜访周报({begin_date}~{end_date}).md"

        filepath = os.path.join(reports_dir, filename)

        # Write report to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"  → Report saved to: {filepath}")

        # Convert markdown to PDF using markdown_pdf library
        pdf_filepath = os.path.join(reports_dir, filename.replace(".md", "") + ".pdf")
        try:
            logger.info(f"  → Converting markdown to PDF: {pdf_filepath}")
            # Initialize PDF object (toc_level=2 means generate table of contents up to level 2 headings, set to 0 for no toc)
            pdf = MarkdownPdf(toc_level=2)

            # Read markdown content
            with open(filepath, "r", encoding="utf-8") as f:
                md_content = f.read()

            # Add content as a PDF section with A4 paper size
            pdf.add_section(Section(md_content, paper_size="A4"))

            # Save PDF file
            pdf.save(pdf_filepath)
            logger.info(f"  → Report converted to PDF: {pdf_filepath}")
            return {"report_file_path": pdf_filepath}
        except Exception as e:
            logger.error(f"  ✗ Failed to convert markdown to PDF: {e}", exc_info=True)
            return {"error_message": f"Failed to convert markdown to PDF: {e}"}

    except Exception as e:
        logger.error(f"  ✗ Writing report failed: {e}", exc_info=True)
        return { "error_message": f"Writing report failed: {e}" }

async def should_push_report(state: ManagerReportState, config: RunnableConfig) -> bool:
    """
    Check if report should be pushed based on state and config
    """
    # Check if push is enabled in config
    configurable = config.get('configurable', {}) if config else {}
    push_enabled = configurable.get('push_enabled', False)

    if not push_enabled:
        logger.info("  → Report push disabled (push_enabled=false)")
        return False

    # 检查是否有数据记录
    has_records = False
    template_data = state.get('template_data', {})

    # 遍历所有模板数据，检查是否有记录
    for template_name, data in template_data.items():

        if data:
            try:
                # 处理数据
                parsed_data = data

                # 如果是字符串，尝试解析为JSON
                if isinstance(data, str):
                    import json
                    parsed_data = json.loads(data)

                # 检查是否是包含记录的列表
                if isinstance(parsed_data, list) and len(parsed_data) > 0:
                    has_records = True
                    logger.info(f"  → Found {len(parsed_data)} records in template {template_name}")
                    break
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"  → Error processing data for template {template_name}: {e}")
                continue

    if not has_records:
        logger.info("  → Report push skipped (no records found)")
        return False
    return True

async def push_report_node(state: ManagerReportState, config: RunnableConfig) -> Dict:
    """
    Push report to API interface
    """
    try:
        configurable = config.get('configurable', {}) if config else {}
        logger.info(f"  → Pushing report")

        api_token = get_api_token_cached()
        if not api_token:
            logger.error("No API token available for pushing report")
            return {"error_message": "No API token available"}

        report_level = configurable.get('report_level', 'employee')
        report_content_arr = state.get('sections')
        push_type = configurable.get('push_type', 'text')

        push_list = {}
        if report_level == "employee":
            push_list = configurable.get('employees', {})
        elif report_level == "team":
            push_list = configurable.get('team_leader', {})
        elif report_level == "company":
            push_list = configurable.get('company_leaders', {})

        admins = configurable.get('admins', {})
        final_list = {**push_list, **admins}
        logger.debug(f"  → Pushing full list before filter: {final_list}")

        # Apply whitelist and blacklist filters
        white_list = configurable.get('push_whitelist', {})
        black_list = configurable.get('push_blacklist', {})
        if white_list:
            intersect_list = final_list.items() & white_list.items()
            final_list = dict(intersect_list)
        if black_list:
            intersect_list = final_list.items() - black_list.items()
            final_list = dict(intersect_list)

        if not final_list:
            logger.info("  → No users to push report to after filtering")
            return {}

        user_ids = set(final_list.values())

        # 根据push_type选择推送方式
        push_types = [pt.strip() for pt in push_type.split(',')]

        # 初始化结果
        results = []
        logger.info(f"""need push useriD:{user_ids}""")
        # 如果包含'text'，推送文字报告
        if 'text' in push_types:
           for item in report_content_arr:
               msg_text=item['content'].content
               # 调用字符串截断函数处理消息
               title_name = item.get('title_name', TEMPLATE_REGISTRY[item['template_name']].title_name)
               msg_parts = truncate_string_by_utf8_bytes(msg_text, title_name=title_name)
               # 循环发送所有分片消息
               # 最多发送三条消息
               max_messages = 7
               message_count = 0
               for part in msg_parts:
                   if message_count >= max_messages:
                       logger.info(f"已达到最大消息数限制 ({max_messages}条)，停止发送剩余内容")
                       break
                   logger.info(part)
                   text_result = await push_wechat_text(user_ids, part, api_token)
                   logger.info("send success")
                   results.append(text_result)
                   message_count += 1
            
        # 如果包含'file'，推送文件报告
        if 'file' in push_types:
            logger.info(f"  → Pushing file report to users: {final_list}")
            # 推送文件逻辑
            # 1. 首先需要获取文件路径，这里假设报告已经保存到文件
            report_file_path = state.get('report_file_path', '')
            if not report_file_path:
                logger.error("No report file path available for pushing file")
                results.append({"error_message": "No report file path available"})
            else:
                # 2. 上传文件获取media_id
                try:
                    media_id = await uploadFile(report_file_path, api_token)
                    if not media_id:
                        logger.error("Failed to upload file to get media_id")
                        results.append({"error_message": "Failed to upload file to get media_id"})
                    else:
                        # 3. 发送文件
                        try:
                            file_result = await sendFile(list(user_ids), media_id, api_token)
                            results.append(file_result)
                        except Exception as e:
                            logger.error(f"  ✗ Sending file report failed: {e}", exc_info=True)
                            results.append({"error_message": f"Sending file report failed: {e}"})
                except Exception as e:
                    logger.error(f"  ✗ Uploading file failed: {e}", exc_info=True)
                    results.append({"error_message": f"Uploading file failed: {e}"})
        
        # 检查结果是否有错误
        errors = [result.get('error_message') for result in results if result and result.get('error_message')]
        if errors:
            return {"error_message": "; ".join(errors)}
        
        # 返回合并的结果
        merged_result = {}
        for result in results:
            if result:
                merged_result.update(result)
        return merged_result

    except Exception as e:
        logger.error(f"  ✗ Pushing report failed: {e}", exc_info=True)
        return { "error_message": f"Pushing report failed: {e}" }

builder = StateGraph(ManagerReportState)

builder.add_node("prepare_args", prepare_args_node)
builder.add_node("collect_data", collect_data_node)
builder.add_node("generate_template_node", generate_template_node)
builder.add_node("compile_report", compile_report_node)
builder.add_node("write_report", write_report_node)
builder.add_node("push_report", push_report_node)

builder.set_entry_point("prepare_args")
builder.add_edge("prepare_args", "collect_data")
builder.add_conditional_edges(
    "collect_data",
    map_template,
    ["generate_template_node"]
)
builder.add_edge("generate_template_node", "compile_report")
builder.add_edge("compile_report", "write_report")

# Conditional edge: only push report if enabled and content exists
builder.add_conditional_edges(
    "write_report",
    should_push_report,
    {
        True: "push_report",
        False: END
    }
)
builder.add_edge("push_report", END)

dynamic_report = builder.compile()


# Report Generator Subgraph (without write/push)
generator_builder = StateGraph(ManagerReportState)
generator_builder.add_node("prepare_args", prepare_args_node)
generator_builder.add_node("collect_data", collect_data_node)
generator_builder.add_node("generate_template_node", generate_template_node)
generator_builder.add_node("compile_report", compile_report_node)
generator_builder.set_entry_point("prepare_args")
generator_builder.add_edge("prepare_args", "collect_data")
generator_builder.add_conditional_edges(
    "collect_data",
    map_template,
    ["generate_template_node"]
)
generator_builder.add_edge("generate_template_node", "compile_report")
generator_builder.add_edge("compile_report", END)

report_generator = generator_builder.compile()