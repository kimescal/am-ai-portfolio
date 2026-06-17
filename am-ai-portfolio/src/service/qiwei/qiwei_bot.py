#!/usr/bin/env python
# coding=utf-8
# 文档：https://developer.work.weixin.qq.com/document/path/101039

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
import os
import logging
import json
import random
import string
import time
import base64
import hashlib
from urllib.parse import urlparse, parse_qs
from Crypto.Cipher import AES
import requests
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from agents import DEFAULT_AGENT, AgentGraph, get_agent, get_all_agent_info
from langchain_core._api import LangChainBetaWarning
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse  # type: ignore[import-untyped]
from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]
from langgraph.types import Command, Interrupt
from langsmith import Client as LangsmithClient

from agents.tools.sql_query import sql_query
from core import settings
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    Feedback,
    FeedbackResponse,
    ServiceMetadata,
    StreamInput,
    UserInput,
)
from service.utils import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)

from .WXBizJsonMsgCrypt import WXBizJsonMsgCrypt

router = APIRouter()

# 常量定义
CACHE_DIR = "/tmp/llm_demo_cache"
MAX_STEPS = 10

# 配置日志
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )
logger = logging.getLogger(__name__)

def _generate_random_string(length):
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

def _process_encrypted_image(image_url, aes_key_base64):
    """
    下载并解密加密图片

    参数:
        image_url: 加密图片的URL
        aes_key_base64: Base64编码的AES密钥(与回调加解密相同)

    返回:
        tuple: (status: bool, data: bytes/str)
               status为True时data是解密后的图片数据,
               status为False时data是错误信息
    """
    try:
        # 1. 下载加密图片
        logger.info("start encrypting pic: %s", image_url)
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        encrypted_data = response.content
        logger.info("pic load success, size: %d byte", len(encrypted_data))

        # 2. 准备AES密钥和IV
        if not aes_key_base64:
            raise ValueError("AESkey couldn't be empty")

        # Base64解码密钥 (自动处理填充)
        aes_key = base64.b64decode(aes_key_base64 + "=" * (-len(aes_key_base64) % 4))
        if len(aes_key) != 32:
            raise ValueError("invalid AESkey: should be 32 byte")

        iv = aes_key[:16]  # 初始向量为密钥前16字节

        # 3. 解密图片数据
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_data = cipher.decrypt(encrypted_data)

        # 4. 去除PKCS#7填充 (Python 3兼容写法)
        pad_len = decrypted_data[-1]  # 直接获取最后一个字节的整数值
        if pad_len > 32:  # AES-256块大小为32字节
            raise ValueError("invalid padding length (over 32 byte)")

        decrypted_data = decrypted_data[:-pad_len]
        logger.info("pic decrypte succedd , size: %d byte", len(decrypted_data))

        return True, decrypted_data

    except requests.exceptions.RequestException as e:
        error_msg = f"pic load fail : {str(e)}"
        logger.error(error_msg)
        return False, error_msg

    except ValueError as e:
        error_msg = f"wrong config : {str(e)}"
        logger.error(error_msg)
        return False, error_msg

    except Exception as e:
        error_msg = f"error pic process : {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def MakeTextStream(stream_id, content, finish):
    plain = {
                "msgtype": "stream",
                "stream": {
                    "id": stream_id,
                    "finish": finish,
                    "content" : content
                }
            }
    return json.dumps(plain, ensure_ascii=False)

def MakeImageStream(stream_id, image_data, finish):
    image_md5 = hashlib.md5(image_data).hexdigest()
    image_base64 = base64.b64encode(image_data).decode('utf-8')

    plain = {
                "msgtype": "stream",
                "stream": {
                    "id": stream_id,
                    "finish": finish,
                    "msg_item": [
                        {
                            "msgtype": "image",
                            "image": {
                                "base64": image_base64,
                                "md5": image_md5
                            }
                        }
                    ]
                }
            }
    return json.dumps(plain)


# stream_id -> {buffer, finished, created, run_id}
class StreamCache:
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def init_stream(self, stream_id: str, run_id: Optional[str] = None):
        async with self._lock:
            self._store[stream_id] = {
                "buffer": "",
                "finished": False,
                "created": time.time(),
                "run_id": run_id,
            }

    async def append(self, stream_id: str, text: str):
        async with self._lock:
            if stream_id in self._store:
                self._store[stream_id]["buffer"] += text

    async def finish(self, user_id: str, stream_id: str):
        async with self._lock:
            if stream_id in self._store:
                link = f"\n\n[详细信息]({settings.WEB_URL}?user_id={user_id}&thread_id={stream_id})"
                self._store[stream_id]["buffer"] += link
                self._store[stream_id]["finished"] = True

    # return current state
    async def get_snapshot(self, stream_id: str) -> Tuple[str, bool]:
        async with self._lock:
            d = self._store.get(stream_id)
            if not d:
                logger.info('oops! Empty in cache')
                return "", False
            return d["buffer"], d["finished"]

    async def set_run_id(self, stream_id: str, run_id: str):
        async with self._lock:
            if stream_id in self._store:
                self._store[stream_id]["run_id"] = run_id

    async def cleanup(self, ttl_seconds: int = 900):
        now = time.time()
        async with self._lock:
            for sid in list(self._store.keys()):
                if now - self._store[sid]["created"] > ttl_seconds:
                    del self._store[sid]

STREAM_CACHE = StreamCache()



def _to_plain(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return convert_message_content_to_string(content)
    except Exception:
        return str(content)


#build JSON
def build_qiwei_stream_payload(
    stream_id: str,
    full_text: str,
    finished: bool,
    images: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "msgtype": "stream",
        "stream": {
            "id": stream_id,
            "finish": bool(finished),
            "content": full_text
            # "msg_item": [],
        }
    }

    if finished and images:
        payload["stream"]["msg_item"] = [
            {
                "msgtype": "image",
                "image": {"base64": img["base64"], "md5": img["md5"]},
            }
            for img in images[:10]
        ]
    return payload

async def encrpt_msg(
    payload: dict,
    nonce:str,
    timestamp:str,
):
    wxcpt = WXBizJsonMsgCrypt(settings.QIWEI_TOKEN.get_secret_value(), settings.QIWEI_ENCODING_AES_KEY.get_secret_value(), settings.QIWEI_CORP_ID)
    payload_str = json.dumps(payload, ensure_ascii=False)
    # logger.debug('reply:%s', payload_str)
    ret, encrypted = wxcpt.EncryptMsg(payload_str, nonce, timestamp)
    if ret != 0:
        logger.error(f"encrypt msg failed: {ret}")
        return Response(content=f"encrypt msg failed: {ret}", media_type="text/plain")
    return Response(content=encrypted, media_type="text/plain")


async def convert_userid(user_id:str):
    query_str = f"SELECT BADGE FROM qy_user_info_all_v WHERE WECOM_ID = '{user_id}';"
    # query_str = f"""
    # SELECT
    #     q.BADGE,
    #     e.NAME
    # FROM qy_user_info_all_v q
    # LEFT JOIN emp_key_info e ON q.BADGE = e.BADGE
    # WHERE q.WECOM_ID = '{user_id}'
    # """

    result = sql_query.invoke({"query":query_str})
    result_list = json.loads(result)

    if result_list and len(result_list) > 0:
        badge = result_list[0]["BADGE"]
        # name = result_list[0]["NAME"]
        return badge

    return user_id

# write into cache
async def generate_full_answer_to_cache(
    stream_id: str,
    user_text: str,
    user_id: str,
    agent_id: str = DEFAULT_AGENT,
):
    agent: AgentGraph = get_agent(agent_id)
    # logger.debug("began to generate answer")
    # the kwargs
    thread_id = stream_id
    # user_id = str(uuid4())
    run_uuid = uuid4()
    thread_name = user_text
    config = RunnableConfig(configurable={"thread_id": thread_id, "model": settings.DEFAULT_MODEL, "user_id": user_id, "thread_name": thread_name}, run_id=run_uuid)
    input_payload = {"messages": [HumanMessage(content=user_text)]}
    kwargs = {"input": input_payload, "config": config}

    logger.info(f"began to generate answer, {kwargs}")

    # run_id
    await STREAM_CACHE.set_run_id(stream_id, str(run_uuid))

    async for ev in agent.astream(**kwargs, stream_mode=["updates","messages"], subgraphs=True):
        if not isinstance(ev, tuple):
            logger.warning("skip non-tuple event: %r", ev)
            continue
        if len(ev) == 3:
            _, mode, event = ev
        else:
            mode, event = ev

        if mode == "updates":
            if isinstance(event, dict) and "__interrupt__" in event:
                logger.info("interrupt detected: %r", event["__interrupt__"])
                break
            continue

        if mode == "messages":
            if not (isinstance(event, tuple) and len(event) == 2):
                logger.warning("unexpected messages event: %r", event)
                continue
            msg, metadata = event

            # 过滤掉来自 intent_guard 节点的消息
            node_name = metadata.get("langgraph_node") or metadata.get("node")
            logger.info(f"node_name:{node_name}")
            # 过滤掉来自 intent_guard 节点的消息
            if metadata and node_name == "intent_guard":
                continue

            tags = metadata.get("tags", []) if isinstance(metadata, dict) else []
            if "skip_stream" in tags:
                logger.info("skip_stream tagged, skipping this message chunk")
                continue

            if isinstance(msg, AIMessageChunk) or \
                (isinstance(msg, AIMessage) and msg.content.strip() != 'Transferring back to supervisor'):
                content = msg.content
            else:
                # logger.warning("non-AI message type: %r", type(msg))
                continue

            if not content:
                continue
            try:
                content = remove_tool_calls(content)
                text = convert_message_content_to_string(content)
            except Exception:
                text = str(content)

            if not text:
                continue

            await STREAM_CACHE.append(stream_id, text)

    await STREAM_CACHE.finish(user_id, stream_id)

@router.get("/qiwei/")
async def verify_url(
    request: Request,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str
):
    logger.debug("received get requst, msg_signature=%s, timestamp=%s, nonce=%s, echostr=%s", msg_signature, timestamp, nonce, echostr)
    wxcpt = WXBizJsonMsgCrypt(settings.QIWEI_TOKEN.get_secret_value(), settings.QIWEI_ENCODING_AES_KEY.get_secret_value(), settings.QIWEI_CORP_ID)

    ret, echostr = wxcpt.VerifyURL(
        msg_signature,
        timestamp,
        nonce,
        echostr
    )
    print(ret)

    if ret != 0:
        echostr = "verify fail"

    return Response(content=echostr, media_type="text/plain")

@router.post("/qiwei/")
async def handle_message(
    request: Request,
    msg_signature: str = None,
    timestamp: str = None,
    nonce: str = None
):
    query_params = dict(request.query_params)
    if not all([msg_signature, timestamp, nonce]):
        raise HTTPException(status_code=400, detail="lack essential parameter")
    logger.debug("received post request, msg_signature=%s, timestamp=%s, nonce=%s", msg_signature, timestamp, nonce)

    post_data = await request.body()

    wxcpt = WXBizJsonMsgCrypt(settings.QIWEI_TOKEN.get_secret_value(), settings.QIWEI_ENCODING_AES_KEY.get_secret_value(), settings.QIWEI_CORP_ID)

    ret, msg = wxcpt.DecryptMsg(
        post_data,
        msg_signature,
        timestamp,
        nonce
    )

    if ret != 0:
        raise HTTPException(status_code=400, detail="decryption failed")

    data = json.loads(msg)
    if 'msgtype' not in data:
        logger.error(f"unknown msgtype: {data}")
        return Response(content=f"unknown msgtype: {data}", media_type="text/plain")

    user_id = data['from']['userid']
    user_id = await convert_userid(user_id)

    msgtype = data['msgtype']
    if msgtype == "text":
        user_text = data["text"]["content"]
        if (user_text == "上上下下左右左右baba"):
            payload = settings.QIWEI_WELCOME_TEMPALTE.replace("{user_id}", user_id)
            ret, encrypted = wxcpt.EncryptMsg(payload, nonce, timestamp)
            if ret != 0:
                logger.error(f"encrypt msg failed: {ret}")
                return Response(content=f"encrypt msg failed: {ret}", media_type="text/plain")
            return Response(content=encrypted, media_type="text/plain")

        stream_id = str(uuid4())
        await STREAM_CACHE.init_stream(stream_id)

        asyncio.create_task(generate_full_answer_to_cache(stream_id, user_text, user_id))
        full_text, finished = await STREAM_CACHE.get_snapshot(stream_id)

        # finish=False, content
        payload = build_qiwei_stream_payload(
            stream_id=stream_id,
            full_text=full_text,
            finished=finished,
        )

        return await encrpt_msg(payload,nonce,timestamp)

    #  stream return the last state
    elif msgtype == "stream":
        stream_id = data["stream"]["id"]
        full_text, finished = await STREAM_CACHE.get_snapshot(stream_id)

        payload = build_qiwei_stream_payload(
            stream_id=stream_id,
            full_text=full_text,
            finished=finished,
            # images=optional_images_if_finished
        )
        return await encrpt_msg(payload,nonce,timestamp)

    elif(msgtype == 'image'):
        logger.warning("need support image msg type")

        payload = {
            "msgtype":"text",
            "text": {
                "content":"对不起, 暂不支持图片消息"
            }
        }
        return await encrpt_msg(payload,nonce,timestamp)

    elif (msgtype == 'mixed'):
        # TODO 处理图文混排消息
        logger.warning("need support mixed msg type")
        payload = {
            "msgtype":"text",
            "text": {
                "content":"对不起, 暂不支持图片混合消息"
            }
        }
        return await encrpt_msg(payload,nonce,timestamp)



    elif (msgtype == 'event'):

        eventtype = data['event']['eventtype']

        if (eventtype == 'enter_chat'):
            payload = settings.QIWEI_WELCOME_TEMPALTE.replace("{user_id}", user_id)
            ret, encrypted = wxcpt.EncryptMsg(payload, nonce, timestamp)
            if ret != 0:
                logger.error(f"encrypt msg failed: {ret}")
                return Response(content=f"encrypt msg failed: {ret}", media_type="text/plain")
            return Response(content=encrypted, media_type="text/plain")

        elif(eventtype == 'template_card_event'):
            return 0
        else:
            logger.warning("unkown eventtype")


        logger.warning("need support event msg type: %s", data)
        return
    else:
        logger.warning("invalid msg type: %s", msgtype)
        return
