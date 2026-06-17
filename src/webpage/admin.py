"""
Admin Dashboard Module
管理员页面 - 查看所有用户对话历史
"""
import os
import asyncio

import streamlit as st
from dotenv import load_dotenv

from client import AgentClient, AgentClientError
from schema import ChatMessage
from webpage.utils import load_css, init_agent_client

APP_TITLE = "AI Portfolio"
APP_ICON = "🤖"


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


async def admin_view() -> None:
    """Admin dashboard view logic."""
    st.set_page_config(
        page_title="Admin Dashboard - " + APP_TITLE,
        page_icon=APP_ICON,
        menu_items={},
        layout="wide"
    )

    load_css("style.css")

    # Header with navigation button
    col_header_title, col_header_btn = st.columns([0.8, 0.2], vertical_alignment="bottom")

    with col_header_title:
        st.markdown('<h1 class="page-title-medium"> 用户对话历史统计</h1>', unsafe_allow_html=True)

    with col_header_btn:
        st.markdown('''
            <div class="nav-button-container">
                <a href="?analytics=true&admin_key=admin123" target="_self" class="nav-button-gradient">
                    查看详细分析统计
                </a>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown('<div class="mb-20"></div>', unsafe_allow_html=True)

    # Initialize client
    agent_client = init_agent_client()

    try:
        with st.spinner("正在加载对话历史中..."):
            response = agent_client.get_all_chats(admin_key="admin123")
        all_chats = response.get("chats", [])

        if not all_chats:
            st.info("暂无对话历史记录")
            return  # Changed from st.stop() to return to avoid sidebar issues

        # Remove duplicate threads
        seen_threads = set()
        unique_chats = []
        for chat in all_chats:
            thread_id = chat.get("thread_id")
            if thread_id and thread_id not in seen_threads:
                seen_threads.add(thread_id)
                unique_chats.append(chat)

        # Group chats by user_id
        user_chats = {}
        for chat in unique_chats:
            user_id = chat.get("user_id", "Unknown User")
            if user_id not in user_chats:
                user_chats[user_id] = []
            user_chats[user_id].append(chat)

        # Create three-column layout
        col1, col2, col3 = st.columns([1.4, 2, 3.2])

        with col1:
            col_title, col_search = st.columns([0.4, 0.6], vertical_alignment="center")
            with col_title:
                st.markdown("<div style='font-size: 18px; font-weight: 600; color: #334155; margin-left: 4px;'>用户列表</div>", unsafe_allow_html=True)
            with col_search:
                 user_search = st.text_input("搜索用户", placeholder="搜索用户", key="user_search", label_visibility="collapsed")

            filtered_users = list(user_chats.keys())
            if user_search:
                filtered_users = [user_id for user_id in filtered_users
                                if user_search.lower() in user_id.lower()]

            if filtered_users:
                with st.container(height=650):
                    def format_user(user_id):
                        """Format user display with badge, name and thread count."""
                        if user_id in user_chats and user_chats[user_id]:
                            user_name = str(user_chats[user_id][0].get("user_name", user_id))
                            thread_count = len(user_chats[user_id])
                            if user_name != user_id:
                                display_name = user_name[:8] + ".." if len(user_name) > 8 else user_name
                                return f"{display_name} ({user_id}) - {thread_count} 个对话"
                            else:
                                return f"{user_id} - {thread_count} 个对话"
                        else:
                            return f"{user_id} - 0 个对话"

                    selected_user = st.radio(
                        "选择用户:",
                        filtered_users,
                        format_func=format_user,
                        key="user_selection"
                    )

        with col2:
            col_title2, col_search2 = st.columns([0.4, 0.6], vertical_alignment="center")
            with col_title2:
                st.markdown("<div style='font-size: 18px; font-weight: 600; color: #334155; margin-left: 4px;'>对话列表</div>", unsafe_allow_html=True)
            with col_search2:
                thread_search = st.text_input("搜索对话", placeholder="搜索对话", key="thread_search", label_visibility="collapsed")

            selected_thread = None
            if 'selected_user' in dir() and selected_user and selected_user in user_chats:
                filtered_threads = user_chats[selected_user]

                # Filter threads by name if search is provided
                if thread_search:
                    filtered_threads = [
                        t for t in filtered_threads 
                        if thread_search.lower() in t.get("thread_name", "").lower()
                    ]
                if filtered_threads:
                    with st.container(height=650):
                        def format_thread(idx):
                            """Format thread display with name and timestamp."""
                            thread = filtered_threads[idx]
                            thread_name = thread.get("thread_name", "Unnamed Chat")
                            display_name = thread_name[:25] + "..." if len(thread_name) > 25 else thread_name
                            
                            # Add timestamp if available
                            timestamp = thread.get('latest_timestamp', '')
                            if timestamp:
                                from datetime import datetime, timezone, timedelta
                                beijing_time = datetime.fromisoformat(timestamp).astimezone(timezone(timedelta(hours=8)))
                                return f"{display_name} ({beijing_time.strftime('%Y-%m-%d %H:%M:%S')})"
                            else:
                                return display_name

                        selected_thread_index = st.radio(
                            "选择对话:",
                            range(len(filtered_threads)),
                            format_func=format_thread,
                            key="thread_selection"
                        )
                        selected_thread = filtered_threads[selected_thread_index]
                else:
                    st.info("该用户暂无对话记录")
            else:
                st.info("请先选择用户")

        with col3:
            col_title3, col_search3 = st.columns([0.4, 0.6], vertical_alignment="center")
            with col_title3:
                st.markdown("<div style='font-size: 18px; font-weight: 600; color: #334155; margin-left: 4px;'>消息内容</div>", unsafe_allow_html=True)
            with col_search3:
                message_search = st.text_input("搜索消息", placeholder="搜索消息", key="message_search", label_visibility="collapsed")

            if selected_thread:
                thread_id = selected_thread.get("thread_id", "Unknown")
                thread_name = selected_thread.get("thread_name", "Unnamed Chat")

                thread_key = f"thread_messages_{thread_id}"
                if thread_key not in st.session_state:
                    try:
                        with st.spinner(f"Loading messages for thread {thread_name}..."):
                            response = agent_client.get_thread_messages(thread_id=thread_id, admin_key="admin123")
                            st.session_state[thread_key] = response.get("messages", [])
                    except AgentClientError as e:
                        st.error(f"Error loading messages: {e}")
                        st.session_state[thread_key] = []

                messages = st.session_state[thread_key]

                if message_search:
                    messages = [
                        msg for msg in messages
                        if message_search.lower() in str(msg.get("content", "")).lower()
                    ]

                if messages:
                    with st.container(height=650):
                        chat_messages = [ChatMessage(**msg_dict) for msg_dict in messages]
                        draw_messages_sync(chat_messages)
                else:
                    st.info("No messages available for this thread.")
            else:
                st.info("Select a thread to view messages.")

    except AgentClientError as e:
        st.error(f"Error retrieving chat data: {e}")
        st.info("Make sure the backend service is running and the admin key is correct.")
