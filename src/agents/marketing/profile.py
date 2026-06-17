import json
import logging
import requests
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import create_react_agent
from core import get_model, settings
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_token_cache = TTLCache(maxsize=1, ttl=settings.PROFILE_TOKEN_TTL)  # 12小时


def get_token(force_refresh: bool = False) -> Optional[str]:
    """
    获取 Profile API 的访问 token，自动缓存12小时
    """
    cache_key = "profile_token"
    
    if not force_refresh and cache_key in _token_cache:
        logger.debug("Using cached token")
        return _token_cache[cache_key]
    
    try:
        url = settings.PROFILE_API_URL
        data = {
            "userCode": settings.PROFILE_USER_CODE,
            "password": settings.PROFILE_PASSWORD.get_secret_value() if settings.PROFILE_PASSWORD else None
        }
        
        response = requests.post(
            url, 
            json=data, 
            headers={"Content-Type": "application/json"}, 
            timeout=30
        )
        
        if response.status_code == 200:
            token = response.json().get("token")
            if token:
                _token_cache[cache_key] = token
                logger.info("Successfully obtained profile token")
                return token
        
        logger.error(f"Failed to get token: HTTP {response.status_code}")
        return None
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"连接失败: {e}")
        return None
    except requests.exceptions.Timeout:
        logger.error("请求超时")
        return None
    except Exception as e:
        logger.error(f"获取 token 异常: {e}")
        return None


def refresh_token() -> Optional[str]:
    """强制刷新 token"""
    return get_token(force_refresh=True)


def clear_token():
    """清除缓存"""
    _token_cache.clear()


def call_api(state: MessagesState):
    """调用资产画像 API"""
    query = next((m.content for m in reversed(state["messages"]) 
                 if hasattr(m, "type") and m.type == "human"), "")
    
    if not query:
        return {"messages": [AIMessage(content="未收到问题", name="profile")]}

    def _request_api(token: str):
        return requests.post(
            settings.PROFILE_ADDR,
            json={
                "UserId": "1", 
                "UserName": "", 
                "query": query,
                "token": token
            },
            timeout=30
        )

    try:
        # 获取 token
        token = get_token()
        if not token:
            return {"messages": [AIMessage(content="获取 token 失败", name="profile")]}
        
        resp = _request_api(token)
        
        # token 过期，刷新重试
        if resp.status_code in [401, 403]:
            logger.info("Token expired, refreshing...")
            token = refresh_token()
            if not token:
                return {"messages": [AIMessage(content="刷新 token 失败", name="profile")]}
            resp = _request_api(token)

        if resp.status_code != 200:
            return {"messages": [AIMessage(content=f"调用失败: HTTP {resp.status_code}", name="profile")]}

        # 解析 SSE 响应
        answer = ""
        for line in resp.text.split('\n'):
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
                if line and line.startswith('{'):
                    try:
                        data = json.loads(line)
                        if data.get("event") == "message" and "answer" in data:
                            answer += data["answer"]
                    except:
                        pass

        return {"messages": [AIMessage(content=answer or "未获取到内容", name="profile")]}
    
    except requests.exceptions.Timeout:
        return {"messages": [AIMessage(content="请求超时", name="profile")]}
    except requests.exceptions.ConnectionError:
        return {"messages": [AIMessage(content="连接失败", name="profile")]}
    except Exception as e:
        logger.error(f"Profile API error: {e}")
        return {"messages": [AIMessage(content=f"错误: {e}", name="profile")]}


# 构建 graph
builder = StateGraph(MessagesState)
builder.add_node("call_api", call_api)
builder.add_edge(START, "call_api")
builder.add_edge("call_api", END)

profile = builder.compile()
profile.name = "profile"

__all__ = ["profile"]