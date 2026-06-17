import os
import streamlit as st
from dotenv import load_dotenv

from client import AgentClient, AgentClientError


def load_css(file_name):
    """Load CSS from assets folder."""
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", file_name)
    try:
        with open(file_path, encoding="utf-8") as f:
            css_content = f.read()
        st.html(f'<style>{css_content}</style>')
    except FileNotFoundError:
        st.error(f"CSS file not found: {file_path}")


def init_agent_client():
    """Initialize agent client if not already in session state."""
    if "agent_client" not in st.session_state:
        load_dotenv()
        agent_url = os.getenv("AGENT_URL")
        if not agent_url:
            host = os.getenv("HOST", "0.0.0.0")
            port = os.getenv("PORT", 8080)
            agent_url = f"http://{host}:{port}"
        try:
            with st.spinner("正在连接服务..."):
                st.session_state.agent_client = AgentClient(base_url=agent_url)
        except AgentClientError as e:
            st.error(f"Error connecting to agent service at {agent_url}: {e}")
            st.markdown("服务可能正在启动，请稍后重试")
            st.stop()
    return st.session_state.agent_client