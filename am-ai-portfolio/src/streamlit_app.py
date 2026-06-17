import asyncio
import json
import os
import urllib.parse
import uuid
from collections.abc import AsyncGenerator
import pandas as pd
import altair as alt

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError
from datetime import datetime, timedelta
from core.settings import settings

from client import AgentClient, AgentClientError
from schema import ChatHistory, ChatMessage
from schema.task_data import TaskData, TaskDataStatus
from urllib.parse import urlencode

from core.logging_config import setup_logging
setup_logging()

# A Streamlit app for interacting with the langgraph agent via a simple chat interface.
# The app has three main functions which are all run async:

# - main() - sets up the streamlit app and high level structure
# - draw_messages() - draws a set of chat messages - either replaying existing messages
#   or streaming new ones.
# - handle_feedback() - Draws a feedback widget and records feedback from the user.

# The app heavily uses AgentClient to interact with the agent's FastAPI endpoints.


APP_TITLE = "AM AI Portfolio"
APP_ICON = "🧰"
USER_ID_COOKIE = "user_id"

threads = []
st.session_state.thread_name = ""

def load_css(file_name):
    """Load CSS from assets folder relative to this file."""
    file_path = os.path.join(os.path.dirname(__file__), "assets", file_name)
    try:
        with open(file_path, encoding="utf-8") as f:
            css_content = f.read()
        st.html(f'<style>{css_content}</style>')
    except FileNotFoundError:
        st.error(f"CSS file not found: {file_path}")
def get_or_create_user_id() -> str:
    """Check if user id exists in session state or URL parameters, or create a new one if it doesn't exist."""
    # 1. Prioritize Session State (Truth for logged-in users)
    if USER_ID_COOKIE in st.session_state:
        user_id = st.session_state[USER_ID_COOKIE]
        # Force sync to URL if different
        if st.query_params.get(USER_ID_COOKIE) != user_id:
            st.query_params[USER_ID_COOKIE] = user_id
        return user_id

    # 2. Fallback to URL parameters (External links/Bookmarks)
    if USER_ID_COOKIE in st.query_params:
        user_id = st.query_params[USER_ID_COOKIE]
        st.session_state[USER_ID_COOKIE] = user_id
        return user_id

    # Generate a new user_id if not found
    user_id = str(uuid.uuid4())
    # Store in session state for this session
    st.session_state[USER_ID_COOKIE] = user_id
    # Also add to URL parameters so it can be bookmarked/shared
    st.query_params[USER_ID_COOKIE] = user_id
    return user_id
def verify_employee(badge: str) -> tuple[bool, str]:
    """Verify employee badge number via service API."""
    try:
        # 登录验证用独立的轻量级 client，不存 session state
        load_dotenv()
        agent_url = os.getenv("AGENT_URL")
        if not agent_url:
            host = os.getenv("HOST", "0.0.0.0")
            port = os.getenv("PORT", 8080)
            agent_url = f"http://{host}:{port}"
        
        from client import AgentClient
        client = AgentClient(base_url=agent_url, get_info=False)
        result = client.verify_employee(badge)
        if result.get("success"):
            return True, result.get("name", "")
        return False, ""
    except Exception as e:
        st.error(f"验证失败: {e}")
        return False, ""


def show_login_page():
    """Display the login page."""
    st.set_page_config(
        page_title="AI资管营销助理 - 登录",
        page_icon="🔐",
        layout="wide"
    )
    
    load_css("style.css")
    
    # Main layout: Left content, Right login
    left_col, right_col = st.columns([3, 2])
    
    # Left side: Content
    with left_col:
        st.markdown("""
        <div class="main-header">
            <div class="main-title"> AI资管营销助理</div>
            <div class="main-subtitle">新一代智能营销数据平台，激发业务无限可能</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 功能卡片数据
        FEATURE_CARDS = [
            ("智能拜访管理", "全流程跟踪客户拜访记录，AI 辅助生成总结，精准洞察客户动态与意向。",
             "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"),
            ("产品知识图谱", "快速检索产品详细信息，掌握核心配置策略，为客户提供专业的咨询服务。",
             "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"),
            ("业绩增长分析", "多维度可视化业绩报表，数据驱动决策，实时监控团队与个人绩效表现。",
             "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"),
            ("客户360°画像", "深度构建客户画像，精准定位潜在需求，实现个性化营销推荐与服务。",
             "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"),
            ("需求智能匹配", "智能分析客户意向，自动匹配最佳产品方案，提高成单转化率与客户满意度。",
             "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"),
            ("持有人服务", "精细化管理产品持有人，提供专属售后服务与持续关怀，增强客户粘性。",
             "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"),
        ]
        
        def render_card(title: str, desc: str, icon_path: str):
            st.markdown(f'''
            <div class="business-card">
                <div class="icon-container">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="{icon_path}" />
                    </svg>
                </div>
                <div class="card-title">{title}</div>
                <div class="card-desc">{desc}</div>
            </div>
            ''', unsafe_allow_html=True)
        
        # 3x2 网格渲染
        for i in range(0, len(FEATURE_CARDS), 2):
            col1, col2 = st.columns(2)
            with col1:
                render_card(*FEATURE_CARDS[i])
            if i + 1 < len(FEATURE_CARDS):
                with col2:
                    render_card(*FEATURE_CARDS[i + 1])
    
    # Right side: Login form
    with right_col:
        st.markdown('<div class="login-spacer"></div>', unsafe_allow_html=True)
        
        st.markdown('<div class="login-title">欢迎回来</div>', unsafe_allow_html=True)
        st.markdown('<p class="login-subtitle">使用企业工号登录系统</p>', unsafe_allow_html=True)

        # Use st.form to enable Enter key submission
        with st.form("login_form", border=False):
            badge = st.text_input("工号", placeholder="请输入您的工号", key="login_badge")
            submit_button = st.form_submit_button("登录", use_container_width=True)
            
            if submit_button:
                if not badge.strip():
                    st.toast("请输入工号")
                else:
                    with st.spinner("正在验证..."):
                        # Simulate a small delay for better UX if verification is too fast
                        import time
                        time.sleep(0.5) 
                        success, name = verify_employee(badge.strip())
                        
                    if success:
                        st.session_state.logged_in = True
                        st.session_state.user_badge = badge.strip()
                        st.session_state.user_name = name
                        st.session_state[USER_ID_COOKIE] = badge.strip()  # Use badge as user_id
                        st.toast(f"欢迎, {name}!")
                        # Add a small delay to let the toast be seen before rerun
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.toast("工号不存在，请检查后重试")
        
        st.markdown('<div class="login-quote"><div style="margin-top: 5px;">"投资如长跑，稳健致远"</div></div>', unsafe_allow_html=True)
        
async def main() -> None:
    q_admin = st.query_params.get("admin", "")
    if isinstance(q_admin, list): q_admin = q_admin[0]
    admin_mode = str(q_admin).lower() == "true"
    
    q_analytics = st.query_params.get("analytics", "")
    if isinstance(q_analytics, list): q_analytics = q_analytics[0]
    analytics_mode = str(q_analytics).lower() == "true"
    
    q_key = st.query_params.get("admin_key", "")
    if isinstance(q_key, list): q_key = q_key[0]
    admin_key = str(q_key)

    if admin_mode and admin_key == "admin123":
        from webpage.admin import admin_view
        await admin_view()
        return
    
    if analytics_mode and admin_key == "admin123":
        from webpage.analytics import analytics_view
        await analytics_view()
        return
    
    if not st.session_state.get("logged_in", False):
        show_login_page()
        return

    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        menu_items={},
        layout="wide"
    )


    # Set chat container width to 2/3 of remaining space
    # st.html(
    #     """
    #     <style>
    #         .stChatFloatingInputContainer {
    #             width: 66.66% !important;
    #         }
    #         .stChatMessage {
    #             width: 66.66% !important;
    #         }
    #     </style>
    #     """,
    # )

    # Hide the streamlit upper-right chrome
    load_css("style.css")
    if st.get_option("client.toolbarMode") != "minimal":
        st.set_option("client.toolbarMode", "minimal")
        await asyncio.sleep(0.1)
        st.rerun()

    # Get or create user ID
    user_id = get_or_create_user_id()

    if "agent_client" not in st.session_state:
        load_dotenv()
        agent_url = os.getenv("AGENT_URL")
        if not agent_url:
            host = os.getenv("HOST", "0.0.0.0")
            port = os.getenv("PORT", 8080)
            agent_url = f"http://{host}:{port}"
        try:
            with st.spinner("Connecting to agent service..."):
                st.session_state.agent_client = AgentClient(base_url=agent_url)
        except AgentClientError as e:
            st.error(f"Error connecting to agent service at {agent_url}: {e}")
            st.markdown("The service might be booting up. Try again in a few seconds.")
            st.stop()
    agent_client: AgentClient = st.session_state.agent_client

    if "thread_id" not in st.session_state:
        thread_id = st.query_params.get("thread_id")
        if not thread_id:
            thread_id = str(uuid.uuid4())
            # threads.append(thread_id)
            # st.query_params["thread_id"] = thread_id
            messages = []
        else:
            try:
                messages: ChatHistory = agent_client.get_history(thread_id=thread_id).messages
            except AgentClientError:
                st.error("No message history found for this Thread ID.")
                messages = []
        st.session_state.messages = messages
        st.session_state.thread_id = thread_id
        
    
    with st.sidebar:
    
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
                <span style="font-size: 24px;">🧰</span>
                <span style="font-size: 20px; font-weight: 700; color: #1e293b;">AI资管营销助理</span>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # 用户信息和退出按钮
        user_name = st.session_state.get("user_name", "用户")
        st.markdown(
            f"""
            <div style='color: #475569; font-size: 16px; font-weight: 500; margin-bottom: 12px;'>
                欢迎回来, {user_name}
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        if st.button(" 退出登录", key="logout_btn", use_container_width=True, type="primary"):
                st.session_state.logged_in = False
                st.session_state.user_badge = ""
                st.session_state.user_name = ""
                st.rerun()
        
        st.divider()


        # Display user ID (for debugging or user information)
        # st.text_input("User ID (read-only)", value=user_id, disabled=True)

        # @st.dialog("Architecture")
        # def architecture_dialog() -> None:
        #     st.image(
        #         "https://github.com/JoshuaC215/agent-service-toolkit/blob/main/media/agent_architecture.png?raw=true"
        #     )
        #     "[View full size on Github](https://github.com/JoshuaC215/agent-service-toolkit/blob/main/media/agent_architecture.png)"
        #     st.caption(
        #         "App hosted on [Streamlit Cloud](https://share.streamlit.io/) with FastAPI service running in [Azure](https://learn.microsoft.com/en-us/azure/app-service/)"
        #     )

        # if st.button(":material/schema: Architecture", use_container_width=True):
        #     architecture_dialog()

        # with st.popover(":material/policy: Privacy", use_container_width=True):
        #     st.write(
        #         "Prompts, responses and feedback in this app are anonymously recorded and saved to LangSmith for product evaluation and improvement purposes only."
        #     )



        @st.dialog("Share/resume chat")
        def share_chat_dialog() -> None:
            session = st.runtime.get_instance()._session_mgr.list_active_sessions()[0]
            st_base_url = urllib.parse.urlunparse(
                [session.client.request.protocol, session.client.request.host, "", "", "", ""]
            )
            # if it's not localhost, switch to https by default
            if not st_base_url.startswith("https") and "localhost" not in st_base_url:
                st_base_url = st_base_url.replace("http", "https")
            # Include both thread_id and user_id in the URL for sharing to maintain user identity
            chat_url = (
                f"{st_base_url}?thread_id={st.session_state.thread_id}&{USER_ID_COOKIE}={user_id}"
            )
            st.markdown(f"**Chat URL:**\n```text\n{chat_url}\n```")
            st.info("Copy the above URL to share or revisit this chat")

        # col1, col2  = st.columns([1,1])
        # with col1:
        #     if st.button(":material/settings: Setting", use_container_width=True):
        #         config_dialog()
        use_streaming = True

        if st.button("新建对话", use_container_width=True):
            st.session_state.messages = []
            st.session_state.thread_id = str(uuid.uuid4())
            st.query_params['user_id'] = user_id
            # st.session_state.threads.append(st.session_state.thread_id)
            st.query_params['thread_id'] = st.session_state.thread_id
            st.session_state.thread_name = ""
            st.rerun()

        st.markdown("##### 历史对话")
        threads = agent_client.get_threads(user_id=st.session_state["user_id"])
        list_container = st.container(height=600)
        with list_container:
            for thread in reversed(threads):
                thread_id = thread["thread_id"]
                thread_name = thread["thread_name"]
                thread_name_display= thread_name[:25]
                if st.button(thread_name_display, key=thread_id, use_container_width=True):
                    st.query_params['user_id'] = user_id
                    st.query_params['thread_id'] = thread_id
                    st.session_state.messages = []
                    messages: ChatHistory = agent_client.get_history(thread_id=thread_id).messages
                    st.session_state.messages = messages
                    st.session_state.thread_name = thread_name

                # url = "?" + urlencode({"user_id": user_id, "thread_id": thread_id})
                # st.link_button(f"{thread_id}", url)



    # Draw existing messages
    messages: list[ChatMessage] = st.session_state.messages

    auto_question = None

    show_welcome = len(messages) == 0 and "pending_question" not in st.session_state

    welcome_placeholder = st.empty()
    
    if show_welcome:
        with welcome_placeholder.container():
        # match agent_client.agent:
        #     case "chatbot":
        #         WELCOME = "Hello! I'm a simple chatbot. Ask me anything!"
        #     case "interrupt-agent":
        #         WELCOME = "Hello! I'm an interrupt agent. Tell me your birthday and I will predict your personality!"
        #     case "research-assistant":
        #         WELCOME = "Hello! I'm an AI-powered research assistant with web search and a calculator. Ask me anything!"
        #     case "rag-assistant":
        #         WELCOME = """Hello! I'm an AI-powered Company Policy & HR assistant with access to AcmeTech's Employee Handbook.
        #         I can help you find information about benefits, remote work, time-off policies, company values, and more. Ask me anything!"""
        #     case _:
        #         WELCOME = "Hello! I'm an AI agent. Ask me anything!"

            with st.chat_message("ai"):
                st.markdown("**欢迎使用 AI 资管营销助理**")
                st.markdown("")
                st.markdown("""您好，我是专门服务于资管市场团队的AI智能体，可以为您提供一站式的数字化营销服务。
目前我已经对接了客户拜访、机构客户需求、产品基本信息及业绩等业务数据，可以回答以下几类典型问题""")
            
            # Clickable question buttons
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button(" 客户拜访及需求 ›", use_container_width=True, key="q_visit"):
                    welcome_placeholder.empty()
                    st.session_state.pending_question = "最近华东区域的客户有什么重点关注？"
                    st.rerun()
            with col2:
                if st.button(" 产品基本信息 ›", use_container_width=True, key="q_product"):
                    welcome_placeholder.empty()
                    st.session_state.pending_question = "星云88号产品信息"
                    st.rerun()
            with col3:
                if st.button(" 产品业绩情况 ›", use_container_width=True, key="q_perf"):
                    welcome_placeholder.empty()
                    st.session_state.pending_question = "星云88号的业绩如何"
                    st.rerun()
            with col4:
                if st.button(" 客户资管画像 ›", use_container_width=True, key="q_profile"):
                    welcome_placeholder.empty()
                    st.session_state.pending_question = "三一集团的资管画像"
                    st.rerun()

    # draw_messages() expects an async iterator over messages
    async def amessage_iter() -> AsyncGenerator[ChatMessage, None]:
        for m in messages:
            yield m

    await draw_messages(amessage_iter())

    # Generate new message if the user provided new input
    user_input = None
    if "pending_question" in st.session_state:
        user_input = st.session_state.pending_question
        del st.session_state.pending_question
    elif chat_input := st.chat_input("请输入您的问题，通过Enter进行发送"):
        user_input = chat_input
    
    # Generate new message if there is input
    if user_input:
        welcome_placeholder.empty()
        if not st.session_state.thread_name:
            st.session_state.thread_name = user_input
        messages.append(ChatMessage(type="human", content=user_input))
        st.chat_message("human").write(user_input)
        try:
            # if st.session_state["use_streaming"]:
            if use_streaming:
                stream = agent_client.astream(
                    message=user_input,
                    # model=st.session_state["model"],
                    thread_id=st.session_state.thread_id,
                    user_id=user_id,
                    thread_name=st.session_state.thread_name,
                )
                await draw_messages(stream, is_new=True)
            else:
                response = await agent_client.ainvoke(
                    message=user_input,
                    # model=st.session_state["model"],
                    thread_id=st.session_state.thread_id,
                    user_id=user_id,
                    thread_name=st.session_state.thread_name,
                )
                messages.append(response)
                st.chat_message("ai").write(response.content)
            st.rerun()  # Clear stale containers
        except AgentClientError as e:
            st.error(f"Error generating response: {e}")
            st.stop()

    # If messages have been generated, show feedback widget
    if len(messages) > 0 and st.session_state.last_message:
        with st.session_state.last_message:
            await handle_feedback()


TYPING_HTML = """
<div class="typing-dots">
  <span></span><span></span><span></span>
</div>
"""


def draw_messages_sync(messages: list[ChatMessage]) -> None:
    """
    Synchronous version of draw_messages for use in the admin page.
    
    This function draws chat messages with proper formatting for different message types:
    - human: User messages
    - ai: AI responses, including tool calls
    - tool: Tool execution results
    - custom: Custom message types
    
    Args:
        messages: List of ChatMessage objects to display
    """
    # Keep track of the status containers for tool calls
    call_results = {}
    
    # Draw each message according to its type
    for msg in messages:
        match msg.type:
            case "human":
                st.chat_message("human").write(msg.content)
            case "ai":
                with st.chat_message("ai"):
                    # If the message has content, write it out.
                    if msg.content:
                        st.write(msg.content)
                    
                    # Handle tool calls if present
                    if msg.tool_calls:
                        # Create a status container for each tool call and store the
                        # status container by ID to ensure results are mapped to the
                        # correct status container.
                        call_results = {}
                        for tool_call in msg.tool_calls:
                            status = st.status(
                                f"""Tool Call: {tool_call["name"]}""",
                                state="complete",
                            )
                            call_results[tool_call["id"]] = status
                            status.write("Input:")
                            status.write(tool_call["args"])
            case "tool":
                # Check if this tool message corresponds to a stored status container
                if msg.tool_call_id in call_results:
                    status = call_results[msg.tool_call_id]
                    status.write("Output:")
                    status.write(msg.content)
                    status.update(state="complete")
                else:
                    st.chat_message("tool").write(msg.content)
            case "custom":
                st.chat_message("assistant").write(msg.content)
            case _:
                st.chat_message("user").write(f"**Unknown Type ({msg.type}):** {msg.content}")


async def draw_messages(
    messages_agen: AsyncGenerator[ChatMessage | str, None],
    is_new: bool = False,
) -> None:
    """
    Draws a set of chat messages - either replaying existing messages
    or streaming new ones.

    This function has additional logic to handle streaming tokens and tool calls.
    - Use a placeholder container to render streaming tokens as they arrive.
    - Use a status container to render tool calls. Track the tool inputs and outputs
      and update the status container accordingly.

    The function also needs to track the last message container in session state
    since later messages can draw to the same container. This is also used for
    drawing the feedback widget in the latest chat message.

    Args:
        messages_aiter: An async iterator over messages to draw.
        is_new: Whether the messages are new or not.
    """

    # Keep track of the last message container
    last_message_type = None
    st.session_state.last_message = None

    # Placeholder for intermediate streaming tokens
    streaming_content = ""
    streaming_placeholder = None
    typing_placeholder = None
    body_container = None
    footer_container = None

    if is_new:
        last_message_type = "ai"
        st.session_state.last_message = st.chat_message("ai")
        with st.session_state.last_message:
            body_container = st.container()
            footer_container = st.container()
            typing_placeholder = footer_container.empty()
            typing_placeholder.html(TYPING_HTML)
    # Iterate over the messages and draw them
    while msg := await anext(messages_agen, None):
        # str message represents an intermediate token being streamed
        if isinstance(msg, str):
            # If placeholder is empty, this is the first token of a new message
            # being streamed. We need to do setup.

            if not streaming_placeholder:
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")
                with (body_container or st.session_state.last_message):
                    streaming_placeholder = st.empty()

            streaming_content += msg
            streaming_placeholder.write(streaming_content)
            continue

        if not isinstance(msg, ChatMessage):
            st.error(f"Unexpected message type: {type(msg)}")
            st.write(msg)
            st.stop()

        match msg.type:
            # A message from the user, the easiest case
            case "human":
                last_message_type = "human"
                st.chat_message("human").write(msg.content)

            # A message from the agent is the most complex case, since we need to
            # handle streaming tokens and tool calls.
            case "ai":
                # If we're rendering new messages, store the message in session state
                if is_new:
                    st.session_state.messages.append(msg)

                # If the last message type was not AI, create a new chat message
                if last_message_type != "ai":
                    last_message_type = "ai"
                    st.session_state.last_message = st.chat_message("ai")

                with (body_container or st.session_state.last_message):
                    # If the message has content, write it out.
                    # Reset the streaming variables to prepare for the next message.
                    if msg.content:
                        if streaming_placeholder:
                            streaming_placeholder.write(msg.content)
                            streaming_content = ""
                            streaming_placeholder = None
                        else:
                            st.write(msg.content)

                    if msg.tool_calls:
                        # Create a status container for each tool call and store the
                        # status container by ID to ensure results are mapped to the
                        # correct status container.
                        with (body_container or st.session_state.last_message):
                            call_results = {}
                            for tool_call in msg.tool_calls:
                                status = st.status(
                                    f"""Tool Call: {tool_call["name"]}""",
                                    state="running" if is_new else "complete",
                                )
                                call_results[tool_call["id"]] = status
                                status.write("Input:")
                                status.write(tool_call["args"])

                        # Expect one ToolMessage for each tool call.
                            for tool_call in msg.tool_calls:
                                if "transfer_to" in tool_call["name"]:
                                    await handle_agent_msgs(messages_agen, call_results, is_new)
                                    break
                                tool_result: ChatMessage = await anext(messages_agen)

                                if tool_result.type != "tool":
                                    st.error(f"Unexpected ChatMessage type: {tool_result.type}")
                                    st.write(tool_result)
                                    st.stop()

                            # Record the message if it's new, and update the correct
                            # status container with the result
                                if is_new:
                                    st.session_state.messages.append(tool_result)
                                if tool_result.tool_call_id:
                                    status = call_results[tool_result.tool_call_id]
                                status.write("Output:")
                                status.write(tool_result.content)
                                status.update(state="complete")
                                    
            case "custom":
                # CustomData example used by the bg-task-agent
                # See:
                # - src/agents/utils.py CustomData
                # - src/agents/bg_task_agent/task.py
                try:
                    task_data: TaskData = TaskData.model_validate(msg.custom_data)
                except ValidationError:
                    st.error("Unexpected CustomData message received from agent")
                    st.write(msg.custom_data)
                    st.stop()

                if is_new:
                    st.session_state.messages.append(msg)

                if last_message_type != "task":
                    last_message_type = "task"
                    st.session_state.last_message = st.chat_message(
                        name="task", avatar=":material/manufacturing:"
                    )
                    with st.session_state.last_message:
                        status = TaskDataStatus()

                status.add_and_draw_task_data(task_data)

            case "system":
                    # 跳过 SystemMessage（supervisor 系统提示词），不显示
                    continue

            # In case of an unexpected message type, log an error and stop
            case _:
                st.error(f"Unexpected ChatMessage type: {msg.type}")
                st.write(msg)
                st.stop()


async def handle_feedback() -> None:
    """Draws a feedback widget and records feedback from the user."""

    # Keep track of last feedback sent to avoid sending duplicates
    if "last_feedback" not in st.session_state:
        st.session_state.last_feedback = (None, None)

    if "feedback_scores" not in st.session_state:
        st.session_state.feedback_scores = {}

    last_msg = st.session_state.messages[-1]
    if last_msg.type != "ai" or not last_msg.run_id:
        return
    
    latest_run_id = last_msg.run_id
    feedback = st.feedback("stars", key=latest_run_id)

    # If the feedback value or run ID has changed, send a new feedback record
    if feedback is not None and (latest_run_id, feedback) != st.session_state.last_feedback:
        # Normalize the feedback value (an index) to a score between 0 and 1
        normalized_score = (feedback + 1) / 5.0

        agent_client: AgentClient = st.session_state.agent_client
        try:
            await agent_client.acreate_feedback(
                run_id=latest_run_id,
                key="human-feedback-stars",
                score=normalized_score,
                kwargs={"comment": "In-line human feedback"},
            )
        except AgentClientError as e:
            st.error(f"Error recording feedback: {e}")
            st.stop()
        st.session_state.last_feedback = (latest_run_id, feedback)
        st.toast("Feedback recorded", icon=":material/reviews:")


async def handle_agent_msgs(messages_agen, call_results, is_new):
    """
    This function segregates agent output into a status container.
    It handles all messages after the initial tool call message
    until it reaches the final AI message.
    """
    nested_popovers = {}
    # looking for the Success tool call message
    first_msg = await anext(messages_agen)
    if is_new:
        st.session_state.messages.append(first_msg)
    status = call_results.get(getattr(first_msg, "tool_call_id", None))
    # Process first message
    if status and first_msg.content:
        status.write(first_msg.content)
        # Continue reading until finish_reason='stop'
    while True:
        # Check for completion on current message
        finish_reason = getattr(first_msg, "response_metadata", {}).get("finish_reason")
        # Break out of status container if finish_reason is anything other than "tool_calls" (glm might use "tool_callstool_calls")
        if finish_reason is not None and finish_reason not in ["tool_calls", "tool_callstool_calls"]:
            if status:
                status.update(state="complete")
            break
        # Read next message
        sub_msg = await anext(messages_agen)

        if isinstance(sub_msg, str):
            continue

        if is_new:
            st.session_state.messages.append(sub_msg)

        if sub_msg.type == "tool" and sub_msg.tool_call_id in nested_popovers:
            popover = nested_popovers[sub_msg.tool_call_id]
            popover.write("**Output:**")
            popover.write(sub_msg.content)
            first_msg = sub_msg
            continue
        # Display content and tool calls using the same status
        if status:
            if sub_msg.content:
                status.write(sub_msg.content)
            if hasattr(sub_msg, "tool_calls") and sub_msg.tool_calls:
                for tc in sub_msg.tool_calls:
                    popover = status.popover(f"{tc['name']}", icon="🛠️")
                    popover.write(f"**Tool:** {tc['name']}")
                    popover.write("**Input:**")
                    popover.write(tc["args"])
                    # Store the popover reference using the tool call ID
                    nested_popovers[tc["id"]] = popover
        # Update first_msg for next iteration
        first_msg = sub_msg 


if __name__ == "__main__":
    asyncio.run(main())
