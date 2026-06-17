import inspect
import json
import logging
import warnings
import sqlite3
import msgpack
from service.qiwei.qiwei_bot import router as qiwei_bot_router
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Dict
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core._api import LangChainBetaWarning
from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse  # type: ignore[import-untyped]
from langfuse.langchain import CallbackHandler  # type: ignore[import-untyped]
from langgraph.types import Command, Interrupt
from langsmith import Client as LangsmithClient
from pathlib import Path

from agents import DEFAULT_AGENT, AgentGraph, get_agent, get_all_agent_info
from core import settings
from memory import initialize_database, initialize_store
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    Feedback,
    FeedbackResponse,
    ServiceMetadata,
    StreamInput,
    UserInput,
    QueryThreads,
    CAPInput,
)
from service.utils import (
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)

warnings.filterwarnings("ignore", category=LangChainBetaWarning)
logger = logging.getLogger(__name__)


def verify_bearer(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide AUTH_SECRET api key.", auto_error=False)),
    ],
) -> None:
    if not settings.AUTH_SECRET:
        return
    auth_secret = settings.AUTH_SECRET.get_secret_value()
    if not http_auth or http_auth.credentials != auth_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Configurable lifespan that initializes the appropriate database checkpointer and store
    based on settings.
    """
    try:
        # Initialize both checkpointer (for short-term memory) and store (for long-term memory)
        async with initialize_database() as saver, initialize_store() as store:
            # Set up both components
            if hasattr(saver, "setup"):  # ignore: union-attr
                await saver.setup()
            # Only setup store for Postgres as InMemoryStore doesn't need setup
            if hasattr(store, "setup"):  # ignore: union-attr
                await store.setup()

            # Configure agents with both memory components
            agents = get_all_agent_info()
            for a in agents:
                agent = get_agent(a.key)
                # Set checkpointer for thread-scoped memory (conversation history)
                agent.checkpointer = saver
                # Set store for long-term memory (cross-conversation knowledge)
                agent.store = store
            yield
    except Exception as e:
        logger.error(f"Error during database/store initialization: {e}")
        raise


app = FastAPI(lifespan=lifespan)
router = APIRouter(dependencies=[Depends(verify_bearer)])


@router.get("/info")
async def info() -> ServiceMetadata:
    models = list(settings.AVAILABLE_MODELS)
    models.sort()
    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=models,
        default_agent=DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )


async def _handle_input(user_input: UserInput, agent: AgentGraph) -> tuple[dict[str, Any], UUID]:
    """
    Parse user input and handle any required interrupt resumption.
    Returns kwargs for agent invocation and the run_id.
    """
    run_id = uuid4()
    thread_id = user_input.thread_id or str(uuid4())
    user_id = user_input.user_id or str(uuid4())
    thread_name = user_input.thread_name or thread_id

    configurable = {"thread_id": thread_id, "model": settings.DEFAULT_MODEL, "user_id": user_id, "thread_name": thread_name}

    callbacks = []
    if settings.LANGFUSE_TRACING:
        # Initialize Langfuse CallbackHandler for Langchain (tracing)
        langfuse_handler = CallbackHandler()

        callbacks.append(langfuse_handler)

    if user_input.agent_config:
        if overlap := configurable.keys() & user_input.agent_config.keys():
            raise HTTPException(
                status_code=422,
                detail=f"agent_config contains reserved keys: {overlap}",
            )
        configurable.update(user_input.agent_config)

    config = RunnableConfig(
        configurable=configurable,
        run_id=run_id,
        callbacks=callbacks,
    )

    # Check for interrupts that need to be resumed
    state = await agent.aget_state(config=config)
    interrupted_tasks = [
        task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts
    ]

    input: Command | dict[str, Any]
    if interrupted_tasks:
        # assume user input is response to resume agent execution from interrupt
        input = Command(resume=user_input.message)
    else:
        input = {"messages": [HumanMessage(content=user_input.message)]}

    kwargs = {
        "input": input,
        "config": config,
    }

    logger.info(f"began to invoke agent, {kwargs}")

    return kwargs, run_id


@router.post("/{agent_id}/invoke")
@router.post("/invoke")
async def invoke(user_input: UserInput, agent_id: str = DEFAULT_AGENT) -> ChatMessage:
    """
    Invoke an agent with user input to retrieve a final response.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.
    """
    # NOTE: Currently this only returns the last message or interrupt.
    # In the case of an agent outputting multiple AIMessages (such as the background step
    # in interrupt-agent, or a tool step in research-assistant), it's omitted. Arguably,
    # you'd want to include it. You could update the API to return a list of ChatMessages
    # in that case.
    agent: AgentGraph = get_agent(agent_id)
    kwargs, run_id = await _handle_input(user_input, agent)

    try:
        response_events: list[tuple[str, Any]] = await agent.ainvoke(**kwargs, stream_mode=["updates", "values"])  # type: ignore # fmt: skip
        response_type, response = response_events[-1]
        if response_type == "values":
            # Normal response, the agent completed successfully
            output = langchain_to_chat_message(response["messages"][-1])
        elif response_type == "updates" and "__interrupt__" in response:
            # The last thing to occur was an interrupt
            # Return the value of the first interrupt as an AIMessage
            output = langchain_to_chat_message(
                AIMessage(content=response["__interrupt__"][0].value)
            )
        else:
            raise ValueError(f"Unexpected response type: {response_type}")

        output.run_id = str(run_id)
        return output
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error")


async def message_generator(
    user_input: StreamInput, agent_id: str = DEFAULT_AGENT
) -> AsyncGenerator[str, None]:
    """
    Generate a stream of messages from the agent.

    This is the workhorse method for the /stream endpoint.
    """
    agent: AgentGraph = get_agent(agent_id)
    kwargs, run_id = await _handle_input(user_input, agent)

    try:
        # Process streamed events from the graph and yield messages over the SSE stream.
        async for stream_event in agent.astream(
            **kwargs, stream_mode=["updates", "messages", "custom"], subgraphs=True
        ):
            if not isinstance(stream_event, tuple):
                continue
            # Handle different stream event structures based on subgraphs
            if len(stream_event) == 3:
                # With subgraphs=True: (node_path, stream_mode, event)
                _, stream_mode, event = stream_event
            else:
                # Without subgraphs: (stream_mode, event)
                stream_mode, event = stream_event
            new_messages = []
            if stream_mode == "updates":
                for node, updates in event.items():
                    # A simple approach to handle agent interrupts.
                    # In a more sophisticated implementation, we could add
                    # some structured ChatMessage type to return the interrupt value.
                    if node == "__interrupt__":
                        interrupt: Interrupt
                        for interrupt in updates:
                            new_messages.append(AIMessage(content=interrupt.value))
                        continue
                    updates = updates or {}
                    update_messages = updates.get("messages", [])
                    # special cases for using langgraph-supervisor library
                    if node == "supervisor" and update_messages:

                        if isinstance(update_messages[-1], ToolMessage):
                            update_messages = [update_messages[-1]]
                        else:
                            update_messages = []

                    if node in ("dynamic", "requirement", "portfolio","profile","business_goal","qiwei"):
                        if update_messages:
                            update_messages = []
                    new_messages.extend(update_messages)

            if stream_mode == "custom":
                new_messages = [event]

            # LangGraph streaming may emit tuples: (field_name, field_value)
            # e.g. ('content', <str>), ('tool_calls', [ToolCall,...]), ('additional_kwargs', {...}), etc.
            # We accumulate only supported fields into `parts` and skip unsupported metadata.
            # More info at: https://langchain-ai.github.io/langgraph/cloud/how-tos/stream_messages/
            processed_messages = []
            current_message: dict[str, Any] = {}
            for message in new_messages:
                if isinstance(message, tuple):
                    key, value = message
                    # Store parts in temporary dict
                    current_message[key] = value
                else:
                    # Add complete message if we have one in progress
                    if current_message:
                        processed_messages.append(_create_ai_message(current_message))
                        current_message = {}
                    processed_messages.append(message)

            # Add any remaining message parts
            if current_message:
                processed_messages.append(_create_ai_message(current_message))

            for message in processed_messages:
                try:
                    if isinstance(message, ChatMessage) or (getattr(message, "__class__", None) and message.__class__.__name__ == "ChatMessage" and getattr(message.__class__, "__module__", "").endswith("schema.schema")  ):
                        chat_message = message
                    else:
                        chat_message = langchain_to_chat_message(message)

                    chat_message.run_id = str(run_id)
                except Exception as e:
                    logger.error(f"Error parsing message: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected error'})}\n\n"
                    continue
                # LangGraph re-sends the input message, which feels weird, so drop it
                if chat_message.type == "human" and chat_message.content == user_input.message:
                    continue
                yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"

            if stream_mode == "messages":
                if not user_input.stream_tokens:
                    continue
                msg, metadata = event
                if "skip_stream" in metadata.get("tags", []):
                    continue
                if not isinstance(msg, AIMessageChunk):
                    continue
                # For some reason, astream("messages") causes non-LLM nodes to send extra messages.
                # Drop them.
                content = remove_tool_calls(msg.content)
                if content:
                    # Empty content in the context of OpenAI usually means
                    # that the model is asking for a tool to be invoked.
                    # So we only print non-empty content.
                    yield f"data: {json.dumps({'type': 'token', 'content': convert_message_content_to_string(content)})}\n\n"
                # yield f"data: {json.dumps({'type': 'token', 'content': convert_message_content_to_string(msg.content)})}\n\n"
    except Exception as e:
        logger.exception("Error in message generator")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


def _create_ai_message(parts: dict) -> AIMessage:
    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)


def _sse_response_example() -> dict[int | str, Any]:
    return {
        status.HTTP_200_OK: {
            "description": "Server Sent Event Response",
            "content": {
                "text/event-stream": {
                    "example": "data: {'type': 'token', 'content': 'Hello'}\n\ndata: {'type': 'token', 'content': ' World'}\n\ndata: [DONE]\n\n",
                    "schema": {"type": "string"},
                }
            },
        }
    }


@router.post(
    "/{agent_id}/stream",
    response_class=StreamingResponse,
    responses=_sse_response_example(),
)
@router.post("/stream", response_class=StreamingResponse, responses=_sse_response_example())
async def stream(user_input: StreamInput, agent_id: str = DEFAULT_AGENT) -> StreamingResponse:
    """
    Stream an agent's response to a user input, including intermediate messages and tokens.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to all messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.

    Set `stream_tokens=false` to return intermediate messages but not token-by-token.
    """
    return StreamingResponse(
        message_generator(user_input, agent_id),
        media_type="text/event-stream",
    )


@router.post("/feedback")
async def feedback(feedback: Feedback) -> FeedbackResponse:
    """
    Record feedback for a run to LangSmith.

    This is a simple wrapper for the LangSmith create_feedback API, so the
    credentials can be stored and managed in the service rather than the client.
    See: https://api.smith.langchain.com/redoc#tag/feedback/operation/create_feedback_api_v1_feedback_post
    """
    client = LangsmithClient()
    kwargs = feedback.kwargs or {}
    client.create_feedback(
        run_id=feedback.run_id,
        key=feedback.key,
        score=feedback.score,
        **kwargs,
    )
    return FeedbackResponse()


@router.post("/history")
def history(input: ChatHistoryInput) -> ChatHistory:
    """
    Get chat history.
    """
    # TODO: Hard-coding DEFAULT_AGENT here is wonky
    agent: AgentGraph = get_agent(DEFAULT_AGENT)
    try:
        state_snapshot = agent.get_state(
            config=RunnableConfig(configurable={"thread_id": input.thread_id})
        )
        messages: list[AnyMessage] = state_snapshot.values["messages"]
        chat_messages: list[ChatMessage] = [langchain_to_chat_message(m) for m in messages]
        logger.info("history len=%d", len(chat_messages))
        return ChatHistory(messages=chat_messages)
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error")

@app.get("/verify-employee/{badge}")
async def verify_employee(badge: str):
    """Verify employee badge number and return employee name."""
    try:
        from agents.tools.sql_query import sql_query
        query = f"SELECT NAME FROM emp_key_info WHERE BADGE = '{badge}'"
        result = sql_query.invoke({"query": query})
        result_data = json.loads(result)
        
        if isinstance(result_data, list) and len(result_data) > 0 and 'NAME' in result_data[0]:
            return {"success": True, "name": result_data[0]['NAME']}
        return {"success": False, "name": ""}
    except Exception as e:
        logger.error(f"Error verifying employee: {e}")
        return {"success": False, "name": "", "error": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint."""

    health_status = {"status": "ok"}

    if settings.LANGFUSE_TRACING:
        try:
            langfuse = Langfuse()
            health_status["langfuse"] = "connected" if langfuse.auth_check() else "disconnected"
        except Exception as e:
            logger.error(f"Langfuse connection error: {e}")
            health_status["langfuse"] = "disconnected"

    return health_status

@router.get("/admin/teams-config")
async def get_teams_config(admin_key: str = ""):
    """
    Get the dynamically generated teams configuration safely from backend server instead of a local volume mount.
    Required by the analytics page.
    """
    if admin_key != "admin123":
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        from jobs.dynamic_report_job import config as dt_config
        teams_data = dt_config.get_teams()
        return {"success": True, "teams": teams_data}
    except Exception as e:
        logger.error(f"Error fetching teams config: {e}")
        return {"success": False, "error": str(e), "teams": {}}
        
@router.get("/admin/all-chats")
async def get_all_chats(admin_key: str = ""):
    """
    Get all chat threads metadata (admin only).
    Requires admin_key parameter in URL for authentication.
    This endpoint only returns thread metadata, not messages.
    """
    # Simple admin authentication - in production, use proper authentication
    if admin_key != "admin123":  # Simple test key, change in production
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get all threads from database
        if settings.DATABASE_TYPE == "sqlite":
            db_path = Path(settings.SQLITE_DB_PATH)
            if not db_path.exists():
                return {"chats": []}

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            # Get all checkpoints with metadata
            cur.execute("SELECT checkpoint, metadata FROM checkpoints")

            all_chats = []
            user_ids = set()

            for (checkpoint, meta) in cur.fetchall():
                if meta is None:
                    continue

                d = None
                # Parse metadata
                if isinstance(meta, (bytes, bytearray)):
                    try:
                        d = msgpack.unpackb(meta, raw=False)
                    except Exception:
                        try:
                            d = json.loads(meta.decode("utf-8", errors="ignore"))
                        except Exception:
                            d = None
                elif isinstance(meta, str):
                    try:
                        d = json.loads(meta)
                    except Exception:
                        d = None

                if not isinstance(d, dict):
                    continue

                thread_id = d.get("thread_id")
                user_id = d.get("user_id")
                thread_name = d.get("thread_name", "Unnamed Chat")

                if not thread_id or not user_id:
                    continue

                # Extract timestamp from checkpoint data
                latest_timestamp = None
                if checkpoint is not None:
                    try:
                        if isinstance(checkpoint, (bytes, bytearray)):
                            checkpoint_data = msgpack.unpackb(checkpoint, raw=False)
                            if isinstance(checkpoint_data, dict):
                                # Try to get timestamp from ts field
                                latest_timestamp = checkpoint_data.get("ts")
                        elif isinstance(checkpoint, str):
                            checkpoint_data = json.loads(checkpoint)
                            if isinstance(checkpoint_data, dict):
                                latest_timestamp = checkpoint_data.get("ts")
                    except Exception as e:
                        logger.warning(f"Could not parse checkpoint data for thread {thread_id}: {e}")

                all_chats.append({
                    "thread_id": thread_id,
                    "user_id": user_id,
                    "thread_name": thread_name,
                    "latest_timestamp": latest_timestamp,  # 添加时间戳信息
                    "message_count": 0,  # Will be populated when messages are loaded
                    "messages": []  # Messages will be loaded separately
                })

                user_ids.add(user_id)

            # Create user_id to name mapping
            user_mapping = {}
            if user_ids:
                # Query emp_key_info table to get name mappings
                try:
                    # Build SQL query to get name for each user_id
                    user_id_list = ",".join([f"'{uid}'" for uid in user_ids])
                    sql_query = f"SELECT badge, name FROM emp_key_info WHERE badge IN ({user_id_list})"

                    # Execute query using sql_query tool
                    from agents.tools.sql_query import sql_query as execute_sql_query
                    result = execute_sql_query.invoke({"query":sql_query})

                    # Parse the result
                    if result:
                        result_data = json.loads(result)
                        if isinstance(result_data, list):
                            for row in result_data:
                                badge = row.get("badge")
                                name = row.get("name")
                                if badge and name:
                                    user_mapping[badge] = name
                except Exception as e:
                    logger.warning(f"Could not fetch user name mappings: {e}")
                    # If mapping fails, continue without mapping

            # Add user_name to each chat object
            for chat in all_chats:
                user_id = chat.get("user_id")
                chat["user_name"] = user_mapping.get(user_id, user_id)  # Use name if found, otherwise use user_id

            # Sort chats by latest_timestamp in descending order (newest first)
            all_chats.sort(key=lambda x: x.get("latest_timestamp", ""), reverse=True)

            conn.close()
            return {
                "chats": all_chats
            }
        else:
            return {"chats": []}

    except Exception as e:
        logger.error(f"Error getting all chats: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving chat data")


@router.get("/admin/thread-messages")
async def get_thread_messages(thread_id: str, admin_key: str = ""):
    """
    Get messages for a specific thread (admin only).
    This endpoint is called separately when a thread is selected.
    """
    # Simple admin authentication - in production, use proper authentication
    if admin_key != "admin123":  # Simple test key, change in production
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get chat history for this thread
        agent: AgentGraph = get_agent(DEFAULT_AGENT)
        config = RunnableConfig(configurable={"thread_id": thread_id})

        # 获取最新的状态快照以获得时间信息
        state_snapshot = await agent.aget_state(config)
        messages: list[AnyMessage] = state_snapshot.values["messages"]
        chat_messages: list[ChatMessage] = [langchain_to_chat_message(m) for m in messages]

        # 为每条消息添加时间戳信息
        # 使用state_snapshot.created_at作为所有消息的时间戳
        # 在实际应用中，可能需要从历史记录中获取每条消息的具体时间
        created_at = getattr(state_snapshot, 'created_at', None)
        if created_at:
            for chat_msg in chat_messages:
                # 将时间信息添加到custom_data中
                chat_msg.custom_data["timestamp"] = created_at

        return {
            "thread_id": thread_id,
            "messages": chat_messages,
            "message_count": len(chat_messages)
        }

    except Exception as e:
        logger.warning(f"Could not get messages for thread {thread_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Could not retrieve messages for thread {thread_id}")

@app.post("/get_threads")
async def threads_by_user_from_metadata(q: QueryThreads) -> list[dict]:
    if settings.DATABASE_TYPE == "sqlite":
        db_path = Path(settings.SQLITE_DB_PATH)
        if not db_path.exists():
            raise HTTPException(500, f"DB not found: {db_path}")

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("SELECT metadata FROM checkpoints")

        out: list[dict] = []
        seen: set[str] = set()
        user_id = q.user_id

        for (meta,) in cur.fetchall():
            if meta is None:
                continue

            d = None
            # bytes → msgpack → json
            if isinstance(meta, (bytes, bytearray)):
                try:
                    d = msgpack.unpackb(meta, raw=False)
                except Exception:
                    try:
                        d = json.loads(meta.decode("utf-8", errors="ignore"))
                    except Exception:
                        d = None

            elif isinstance(meta, str):
                try:
                    d = json.loads(meta)
                except Exception:
                    d = None

            if not isinstance(d, dict):
                continue

            if d.get("user_id") != user_id:
                continue

            thread_id = d.get("thread_id")
            thread_name = d.get("thread_name")

            if not thread_id or thread_id in seen:
                continue
            seen.add(thread_id)

            out.append({
                "thread_id": thread_id,
                "thread_name": thread_name,
            })

        conn.close()
        return out
    else:
        logger.info("Haven't implemented")
        return []


def convert_cap_to_user_input(cap_input: CAPInput) -> StreamInput:

    # 基础转换
    user_input = StreamInput(
        message=cap_input.question[0]["value"],
        thread_id=cap_input.session_id,
        user_id=cap_input.user_id,
        stream_tokens=True,
    )
    return user_input

def create_tool_call_template(tool_name: str, tool_args: Dict[str, Any]) -> str:
    tool_args_json = json.dumps(tool_args, ensure_ascii=False, indent=2)

    return f"""<details>
  <summary>🛠️工具调用: {tool_name}</summary>

```json
{tool_args_json}
```
</details>"""


def end_tool_call_template(result_content: str) -> str:
    return f"""<details>
  <summary>工具执行结果</summary>

{result_content}
</details>"""

async def cap_format_generator(
    user_input: StreamInput,
) -> AsyncGenerator[str, None]:

    session_id = user_input.thread_id or str(uuid4())

    try:
        agent: AgentGraph = get_agent(DEFAULT_AGENT)
        kwargs, run_id = await _handle_input(user_input, agent)

        start_response = {
            "answer": {
                "answer_id": 1,
                "content": [],
                "finish_reason": "none",
                "step": {"label": "开始处理请求...", "state": "starting"},
            },
            "session_id": session_id,
        }
        yield f"data: {json.dumps(start_response)}\n\n"

        async for stream_event in agent.astream(
            **kwargs, stream_mode=["updates", "messages"], subgraphs=True
        ):
            if not isinstance(stream_event, tuple):
                continue

            if len(stream_event) == 3:
                stream_mode, event = stream_event[1:]
            else:
                stream_mode, event = stream_event

            if stream_mode == "updates":
            
                for node, updates in event.items():
                    if node == "__interrupt__":
                        continue

                    updates = updates or {}
                    update_messages = updates.get("messages", [])

                    if "supervisor" in node and update_messages:

                        if isinstance(update_messages[-1], ToolMessage):
                            update_messages = [update_messages[-1]]
                        else:
                            update_messages = []
                    elif node in ("dynamic", "requirement", "portfolio","qiwei"):
                        update_messages = []
                    
                    for message in update_messages:
                        
                        if not hasattr(message, "tool_calls") or not message.tool_calls:
                            continue

                        for tool_call in message.tool_calls:
                            tool_name = tool_call.get("name", "")
                            tool_args = tool_call.get("args", {})

                            # 跳过配置中需要隐藏的工具
                            hide_tools = settings.HIDE_TOOL_NAMES_LIST
                            if "transfer_to" in tool_name or "transfer_back" in tool_name:
                                continue

                            if tool_name in hide_tools:
                                continue
                            
                            tool_content = create_tool_call_template(tool_name, tool_args)
                            tool_response = {
                                "answer": {
                                    "content": [{"type": "text", "value": tool_content}],
                                    "finish_reason": "none",
                                    "step": {"label": f"调用工具: {tool_name}", "state": "tool_calling"},
                                },
                                "session_id": session_id,
                            }
                            yield f"data: {json.dumps(tool_response)}\n\n"

            elif stream_mode == "messages" and user_input.stream_tokens:
                msg, metadata = event
                # 过滤掉来自 intent_guard 节点的消息
                node_name = metadata.get("langgraph_node") or metadata.get("node")
                logger.info(f"node_name:{node_name}")
                # 过滤掉来自 intent_guard 节点的消息
                if metadata and node_name == "intent_guard":
                    continue
                if isinstance(msg, AIMessageChunk) and msg.content:
                    content = remove_tool_calls(msg.content)
                    if content:
                        content_text = convert_message_content_to_string(content)
                        if content_text.strip():
                            token_response = {
                                "answer": {
                                    "content": [{"type": "text", "value": content_text}],
                                    "finish_reason": "none",
                                    "step": {
                                        "label": "正在回答...",
                                        "state": "answering",
                                    },
                                },
                                "session_id": session_id,
                            }
                            yield f"data: {json.dumps(token_response)}\n\n"

        final_response = {
            "answer": {
                "answer_id": 1,
                "content": [],
                "finish_reason": "stop",
                "step": {"label": "回答完成", "state": "completed"},
            },
            "session_id": session_id,
        }
        yield f"data: {json.dumps(final_response)}\n\n"

    except Exception as e:
        error_response = {
            "answer": {
                "answer_id": 1,
                "content": [{"type": "text", "value": f"错误: {str(e)}"}],
                "finish_reason": "error",
                "step": {"label": "处理出现错误", "state": "error"},
            },
            "session_id": session_id,
        }
        yield f"data: {json.dumps(error_response)}\n\n"

    finally:
        yield "data: [DONE]\n\n"


@router.post("/cap_stream")
async def cap_stream(user_input: CAPInput) -> StreamingResponse:
    """
    {
      "answer": {
        "answer_id": 1,
        "content": [{"type": "text", "value": "内容"}],
        "finish_reason": "none|stop|tool_calls|error",
        "step": {"label": "描述", "state": "状态"}
      },
      "session_id": "threadID"
    }
    """
    converted_input = convert_cap_to_user_input(user_input)
    return StreamingResponse(
        cap_format_generator(converted_input),
        media_type="text/event-stream",
    )
app.include_router(router)
app.include_router(qiwei_bot_router)
