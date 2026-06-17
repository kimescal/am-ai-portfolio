from langchain_core.tools import tool
from agents.tools.sql_query import sql_query
import json

from service.qiwei.zhiyu_platform import push_wechat_text, get_api_token_cached


async def get_badge_by_name(name: str) -> str:
    """根据姓名从emp_key_info表中获取工号

    Args:
        name: 姓名

    Returns:
        str: 工号，如果未找到则返回空字符串
    """
    # 构建SQL查询
    sql_query_str = f"SELECT BADGE FROM emp_key_info WHERE NAME = '{name}'"

    # 执行SQL查询
    sql_result = sql_query.invoke({"query": sql_query_str})

    # 解析SQL结果
    result = json.loads(sql_result)

    # 提取工号
    if result and isinstance(result, list) and len(result) > 0:
        return result[0].get("BADGE", "")
    return ""


@tool
async def qiwei_success_tool(mentioned_names: str):
    """处理发送智域测试数据给指定人员的请求，返回 success 字符串，并拼接上提到的人名和对应的工号

    Args:
        mentioned_names: 以逗号分隔的提到的人名列表，这些人员将收到智域测试数据
    """
    # 处理提到的人名
    names = [name.strip() for name in mentioned_names.split(",") if name.strip()]
    result_parts = ["success"]

    # 获取API token
    api_token = get_api_token_cached()

    # 为每个人名获取工号并发送消息
    for name in names:
        badge = await get_badge_by_name(name)
        result_parts.append(f"{name}:{badge}")

        # 如果获取到了工号，发送消息
        if badge:
            try:
                await push_wechat_text({badge}, "企业微信机器人推送测试success", api_token)
            except Exception as e:
                # 发送消息失败不影响返回结果
                pass

    return ",".join(result_parts)