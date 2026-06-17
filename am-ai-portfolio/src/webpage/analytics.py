"""
Analytics Dashboard Module
统计分析页面 - 用户统计和指标分析
"""
import os
import asyncio
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import altair as alt
from dotenv import load_dotenv
import requests

from client import AgentClient, AgentClientError
from webpage.utils import load_css, init_agent_client

async def analytics_view() -> None:
    """Analytics dashboard view logic."""
    st.set_page_config(
        page_title="Analytics Dashboard",
        page_icon="",
        menu_items={},
        layout="wide"
    )

    load_css("style.css")

    # Header with navigation button
    col_header_title, col_header_btn = st.columns([0.8, 0.2], vertical_alignment="bottom")

    with col_header_title:
        st.markdown('<h1 class="page-title-large"> Analytics Dashboard</h1>', unsafe_allow_html=True)

    with col_header_btn:
        st.markdown('''
            <div class="nav-button-container">
                <a href="?admin=true&admin_key=admin123" target="_self" class="nav-button-gradient">
                    返回对话管理
                </a>
            </div>
        ''', unsafe_allow_html=True)

    # Initialize client
    agent_client = init_agent_client()

    try:
        with st.spinner("Loading data..."):
            response = agent_client.get_all_chats(admin_key="admin123")
            all_chats = response.get("chats", [])
        
        if not all_chats:
            st.info("No data found.")
            st.stop()
        
        # Remove duplicate threads
        seen_threads = set()
        unique_chats = []
        for chat in all_chats:
            thread_id = chat.get("thread_id")
            if thread_id and thread_id not in seen_threads:
                seen_threads.add(thread_id)
                unique_chats.append(chat)
        now = datetime.now()
        # SIDEBAR: Time filter + Basic metrics
        with st.sidebar:
            st.header("统计分析")
            st.markdown("<h4 style='font-size: 1rem; color: #475569;'>时间筛选</h4>", unsafe_allow_html=True)
            date_options = ["全部", "今日", "本周", "本月", "自定义"]
            selected_period = st.selectbox("选择时间范围:", date_options, key="analytics_date_filter")

            if selected_period == "自定义":
                custom_range = st.date_input(
                    "选择日期范围",
                    value=(now - timedelta(days=30), now),
                    key="custom_date_range"
                )

        # Date filtering logic
        end_date = None
        if selected_period == "今日":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif selected_period == "本周":
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif selected_period == "本月":
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif selected_period == "自定义":
            if isinstance(custom_range, tuple) and len(custom_range) == 2:
                start_date = datetime.combine(custom_range[0], datetime.min.time())
                end_date = datetime.combine(custom_range[1], datetime.max.time())
            else:
                start_date = None
        else:
            start_date = None
        
        # Filter chats by date
        filtered_chats = unique_chats
        if start_date:
            filtered_chats = []
            for chat in unique_chats:
                ts = chat.get("latest_timestamp", "")
                if ts:
                    try:
                        chat_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
                        chat_date_naive = chat_date.replace(tzinfo=None)
                        if chat_date_naive >= start_date and (end_date is None or chat_date_naive <= end_date):
                            filtered_chats.append(chat)
                    except:
                        filtered_chats.append(chat)
                else:
                    filtered_chats.append(chat)
        
        # Calculate metrics
        total_threads = len(filtered_chats)
        active_users = len(set(chat.get("user_id", "") for chat in filtered_chats))
        avg_per_user = total_threads / active_users if active_users > 0 else 0

        # Calculate Monthly Average New Users
        user_first_seen = {}
        for chat in unique_chats:
            uid = chat.get("user_id", "")
            ts = chat.get("latest_timestamp", "")
            if uid and ts:
                try:
                    chat_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
                    chat_date = chat_date.replace(tzinfo=None)
                    if uid not in user_first_seen or chat_date < user_first_seen[uid]:
                        user_first_seen[uid] = chat_date
                except:
                    pass
        
        new_users_by_month = {}
        for uid, first_date in user_first_seen.items():
            month_key = first_date.strftime("%Y-%m")
            new_users_by_month[month_key] = new_users_by_month.get(month_key, 0) + 1

        # Calculate retention rate, returning users and net new users based on time filter
        if selected_period == "今日":
            ret_current_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            ret_prev_start = ret_current_start - timedelta(days=1)
            ret_prev_end = ret_current_start
        elif selected_period == "本月":
            ret_current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if ret_current_start.month == 1:
                ret_prev_start = ret_current_start.replace(year=ret_current_start.year - 1, month=12)
            else:
                ret_prev_start = ret_current_start.replace(month=ret_current_start.month - 1)
            ret_prev_end = ret_current_start
        elif selected_period == "全部":
            ret_current_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            ret_prev_start = ret_current_start.replace(year=ret_current_start.year - 1)
            ret_prev_end = ret_current_start
        elif selected_period == "自定义" and start_date and end_date:
            duration = end_date - start_date
            ret_current_start = start_date
            ret_prev_end = start_date
            ret_prev_start = start_date - duration
        else:
            ret_current_start = now - timedelta(days=now.weekday())
            ret_current_start = ret_current_start.replace(hour=0, minute=0, second=0, microsecond=0)
            ret_prev_start = ret_current_start - timedelta(days=7)
            ret_prev_end = ret_current_start

        ret_current_users = set()
        ret_prev_users = set()
        for chat in unique_chats:
            ts = chat.get("latest_timestamp", "")
            uid = chat.get("user_id", "")
            if ts and uid:
                try:
                    chat_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
                    chat_date = chat_date.replace(tzinfo=None)
                    if chat_date >= ret_current_start and (end_date is None or chat_date <= end_date):
                        ret_current_users.add(uid)
                    elif ret_prev_start <= chat_date < ret_prev_end:
                        ret_prev_users.add(uid)
                except:
                    pass
        churned_users = len(ret_prev_users - ret_current_users)
        net_new_users = len(ret_current_users - ret_prev_users)
        new_user_ratio = (net_new_users / len(ret_current_users) * 100) if ret_current_users else 0
        
        
        # SIDEBAR: Display Metrics
        with st.sidebar:
            st.divider()
            st.markdown("<h4 style='font-size: 1rem; color: #475569;'>基础指标</h4>", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                st.metric("总对话数", total_threads)
                st.metric("活跃用户", active_users)
            with col2:
                st.metric("人均对话", f"{avg_per_user:.1f}")
                st.metric("新用户占比", f"{new_user_ratio:.1f}%")
            col3, col4 = st.columns(2)
            with col3:
                 st.metric("流失用户", churned_users)
            with col4:
                st.metric("净增用户", net_new_users)
        
        # MAIN AREA: Detailed analysis
        st.markdown("### 详细分析")
        
        tab_options = ["用户排行", "留存率", "使用趋势", "新增用户", "使用时段热力图", "客户经理使用情况", "问题分类"]
        selected_tab = st.radio(
            "分析类型", tab_options, horizontal=True, key="analytics_selected_tab", label_visibility="collapsed"
        )
        
        if selected_tab == "用户排行":
            st.markdown("#### Top 10 活跃用户")
            user_thread_counts = {}
            for chat in filtered_chats:
                uid = chat.get("user_id", "Unknown")
                uname = chat.get("user_name", uid)
                key = f"{uname} ({uid})"
                user_thread_counts[key] = user_thread_counts.get(key, 0) + 1
            
            if user_thread_counts:
                sorted_users = sorted(user_thread_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                df_ranking = pd.DataFrame(sorted_users, columns=["用户", "对话数"])
                df_ranking.index = range(1, len(df_ranking) + 1)
                df_ranking.index.name = "排名"
                st.dataframe(df_ranking, use_container_width=True)
            else:
                st.info("暂无用户数据")
        
        if selected_tab == "留存率":
            st.markdown("#### 用户留存分析")
            
            if selected_period == "今日":
                current_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                prev_start = current_start - timedelta(days=1)
                prev_end = current_start
                current_label = "今日用户"
                prev_label = "昨日用户"
            elif selected_period == "本月":
                current_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                # Previous month start
                if current_start.month == 1:
                    prev_start = current_start.replace(year=current_start.year - 1, month=12)
                else:
                    prev_start = current_start.replace(month=current_start.month - 1)
                prev_end = current_start
                current_label = "本月用户"
                prev_label = "上月用户"
            elif selected_period == "全部":
                # Yearly comparison
                current_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                prev_start = current_start.replace(year=current_start.year - 1)
                prev_end = current_start
                current_label = "今年用户"
                prev_label = "去年用户"
            elif selected_period == "自定义" and start_date and end_date:
                # Same duration, shifted back
                duration = end_date - start_date
                current_start = start_date
                prev_end = start_date
                prev_start = start_date - duration
                cur_s = start_date.strftime("%m/%d")
                cur_e = end_date.strftime("%m/%d")
                pre_s = prev_start.strftime("%m/%d")
                pre_e = prev_end.strftime("%m/%d")
                current_label = f"{cur_s}-{cur_e} 用户"
                prev_label = f"{pre_s}-{pre_e} 用户"
            else:
                # "本周" or "全部" default to weekly comparison
                current_start = now - timedelta(days=now.weekday())
                current_start = current_start.replace(hour=0, minute=0, second=0, microsecond=0)
                prev_start = current_start - timedelta(days=7)
                prev_end = current_start
                current_label = "本周用户"
                prev_label = "上周用户"
            
            current_users = set()
            prev_users = set()
            
            for chat in unique_chats:
                ts = chat.get("latest_timestamp", "")
                uid = chat.get("user_id", "")
                if ts and uid:
                    try:
                        chat_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
                        chat_date = chat_date.replace(tzinfo=None)
                        if chat_date >= current_start and (end_date is None or chat_date <= end_date):
                            current_users.add(uid)
                        elif prev_start <= chat_date < prev_end:
                            prev_users.add(uid)
                    except:
                        pass
            
            returning_users = current_users & prev_users
            retention_rate_tab = (len(returning_users) / len(prev_users) * 100) if prev_users else 0
            
            ret_col1, ret_col2, ret_col3 = st.columns(3)
            with ret_col1:
                st.metric(current_label, len(current_users))
            with ret_col2:
                st.metric(prev_label, len(prev_users))
            with ret_col3:
                st.metric("留存率", f"{retention_rate_tab:.1f}%")
            
            if returning_users:
                st.caption(f"🔄 回访用户: {len(returning_users)} 人")

        if selected_tab == "使用趋势":
            st.markdown("#### 使用趋势图")
            st.caption("按日期统计对话数量变化")
            
            # Group chats by date (respects time filter)
            daily_counts = {}
            for chat in filtered_chats:
                ts = chat.get("latest_timestamp", "")
                if ts:
                    try:
                        chat_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
                        date_key = chat_date.strftime("%Y-%m-%d")
                        daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
                    except:
                        pass
            
            if daily_counts:
                sorted_dates = sorted(daily_counts.items())
                df_trend = pd.DataFrame(sorted_dates, columns=["日期_排序", "对话数"])
                df_trend["日期"] = df_trend["日期_排序"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d"))
                
                chart = alt.Chart(df_trend).mark_line(point=True).encode(
                    x=alt.X('日期:N', sort=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y('对话数:Q', axis=alt.Axis(tickMinStep=1)),
                    tooltip=['日期', '对话数']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
                
                trend_col1, trend_col2, trend_col3 = st.columns(3)
                with trend_col1:
                    st.metric("活跃天数", len(df_trend))
                with trend_col2:
                    avg_daily = df_trend["对话数"].mean()
                    st.metric("日均对话", f"{avg_daily:.1f}")
                with trend_col3:
                    max_day = df_trend.loc[df_trend["对话数"].idxmax()]
                    st.metric("峰值日", f"{int(max_day['对话数'])} 对话")
            else:
                st.info("暂无数据")

        if selected_tab == "新增用户":
            st.markdown("#### 新增用户趋势")
            st.caption("按周统计首次使用的新用户数量")
            
            if selected_period in ["今日", "本周"]:
                group_mode = "daily"
                x_label = "日期"
                avg_label = "日均新增"
                recent_label = "今日新增" if selected_period == "今日" else "最近新增"
            else:
                group_mode = "weekly"
                x_label = "周起始日"
                avg_label = "周均新增"
                recent_label = "最近一周新增"
            
            if user_first_seen:
                # Filter by selected time period
                filtered_first_seen = user_first_seen
                if start_date:
                    filtered_first_seen = {uid: d for uid, d in user_first_seen.items() if d >= start_date}
                
                grouped_new_users = {}
                for uid, first_date in filtered_first_seen.items():
                    if group_mode == "daily":
                        date_key = first_date.strftime("%Y-%m-%d")
                    else:
                        week_start = first_date - timedelta(days=first_date.weekday())
                        date_key = week_start.strftime("%Y-%m-%d")
                    grouped_new_users[date_key] = grouped_new_users.get(date_key, 0) + 1
                
                sorted_data = sorted(grouped_new_users.items())
                df_new_users = pd.DataFrame(sorted_data, columns=["排序键", "新用户数"])
                df_new_users[x_label] = df_new_users["排序键"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d"))
                
                chart = alt.Chart(df_new_users).mark_bar().encode(
                    x=alt.X(f'{x_label}:N', sort=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y('新用户数:Q', axis=alt.Axis(tickMinStep=1)),
                    tooltip=[x_label, '新用户数']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
                
                new_col1, new_col2, new_col3 = st.columns(3)
                with new_col1:
                    st.metric("新增用户数", len(filtered_first_seen))
                with new_col2:
                    avg_val = df_new_users["新用户数"].mean()
                    st.metric(avg_label, f"{avg_val:.1f}")
                with new_col3:
                    if len(df_new_users) >= 2:
                        recent = int(df_new_users.iloc[-1]["新用户数"])
                        prev = int(df_new_users.iloc[-2]["新用户数"])
                        change = recent - prev
                        st.metric(recent_label, recent, delta=change)
                    else:
                        st.metric(recent_label, int(df_new_users.iloc[-1]["新用户数"]) if len(df_new_users) > 0 else 0)
            else:
                st.info("暂无用户数据")

        if selected_tab == "问题分类":
            st.markdown("#### 问题类型分类")
            
            QUESTION_CATEGORIES = {
                "客户拜访": [],
                "客户需求": [],
                "客户画像": [],
                "产品信息": [],
            }
            
            category_counts = {cat: 0 for cat in QUESTION_CATEGORIES.keys()}
            
            if selected_period == "全部":
                one_month_ago = now - timedelta(days=30)
                classify_chats = []
                for chat in filtered_chats:
                    ts = chat.get("latest_timestamp", "")
                    if ts:
                        try:
                            chat_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
                            if chat_date.replace(tzinfo=None) >= one_month_ago:
                                classify_chats.append(chat)
                        except:
                            classify_chats.append(chat)
                st.caption("统计近一个月用户常问的问题类型")
            else:
                classify_chats = filtered_chats
            
            if classify_chats:
                with st.spinner(f"分析 {len(classify_chats)} 个对话中的问题类型..."):
                    for chat in classify_chats:
                        thread_id = chat.get("thread_id", "")
                        if thread_id:
                            try:
                                messages = agent_client.get_history(thread_id=thread_id).messages
                                
                                for msg in messages:
                                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                        for tool_call in msg.tool_calls:
                                            tool_name = tool_call.get("name", "")
                                            
                                            if "transfer_to_dynamic" in tool_name:
                                                category_counts["客户拜访"] += 1
                                            elif "transfer_to_requirement" in tool_name:
                                                category_counts["客户需求"] += 1
                                            elif "transfer_to_profiler" in tool_name:
                                                category_counts["客户画像"] += 1
                                            elif "transfer_to_portfolio" in tool_name:
                                                category_counts["产品信息"] += 1
                            except:
                                pass
            
            total_questions = sum(category_counts.values())
            
            if total_questions > 0:
                cat_data = [(cat, count) for cat, count in category_counts.items() if count > 0]
                cat_data.sort(key=lambda x: x[1], reverse=True)
                df_cats = pd.DataFrame(cat_data, columns=["类型", "数量"])
                
                cat_col1, cat_col2 = st.columns(2)
                with cat_col1:
                    st.metric("总问题数", total_questions)
                with cat_col2:
                    top_cat = cat_data[0][0] if cat_data else "无"
                    st.metric("最热门类型", top_cat)
                
                chart = alt.Chart(df_cats).mark_bar().encode(
                    x=alt.X('类型:N', sort='-y', axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y('数量:Q'),
                    color=alt.Color('数量:Q', scale=alt.Scale(scheme='blues')),
                    tooltip=['类型', '数量']
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("暂无问题数据")
        
        if selected_tab == "使用时段热力图":
            st.markdown("#### 用户活跃时段分布")
            st.caption("按星期和小时统计对话数量，颜色越深表示越活跃")

            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            heatmap_data = []
            for chat in filtered_chats:
                ts = chat.get("latest_timestamp", "")
                if ts:
                    try:
                        chat_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
                        chat_date = chat_date.replace(tzinfo=None) + timedelta(hours=8)  # UTC -> Beijing
                        heatmap_data.append({
                            "星期": weekday_names[chat_date.weekday()],
                            "小时": chat_date.hour,
                            "weekday_num": chat_date.weekday()
                        })
                    except:
                        pass

            if heatmap_data:
                df_heat = pd.DataFrame(heatmap_data)
                df_counts = df_heat.groupby(["星期", "小时", "weekday_num"]).size().reset_index(name="对话数")

                chart = alt.Chart(df_counts).mark_rect(cornerRadius=3).encode(
                    x=alt.X("小时:O", title="小时", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("星期:N", title="星期",
                            sort=weekday_names),
                    color=alt.Color("对话数:Q",
                                    scale=alt.Scale(scheme="reds"),
                                    legend=alt.Legend(title="对话数")),
                    tooltip=["星期", "小时", "对话数"]
                ).properties(height=280)
                st.altair_chart(chart, use_container_width=True)

                # Summary metrics
                peak = df_counts.loc[df_counts["对话数"].idxmax()]
                heat_col1, heat_col2, heat_col3 = st.columns(3)
                with heat_col1:
                    st.metric("最活跃时段", f"{peak['星期']} {int(peak['小时'])}:00")
                with heat_col2:
                    st.metric("峰值对话数", int(peak["对话数"]))
                with heat_col3:
                    weekday_totals = df_counts.groupby("weekday_num")["对话数"].sum()
                    busiest_day = weekday_names[weekday_totals.idxmax()]
                    st.metric("最繁忙星期", busiest_day)
            else:
                st.info("暂无数据")
        if selected_tab == "客户经理使用情况":
            st.markdown("#### 资管客户经理使用分析")
            st.caption("基于团队配置中的成员工号，匹配对话数据")

            # Load config via cfg module
            try:
                # Add /admin to base URL for admin endpoints
                admin_base_url = f"{agent_client.base_url.rstrip('/')}/admin"
                response = requests.get(
                    f"{admin_base_url}/teams-config",
                    params={"admin_key": "admin123"},
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    teams = data.get("teams", {}) if data.get("success") else {}
                else:
                    st.error(f"加载团队配置失败 (HTTP {response.status_code})")
                    teams = {}
            except Exception as e:
                st.error(f"无法请求团队配置接口: {e}")
                teams = {}

            if teams:
                # Build id->name and id->team mappings
                all_members = {}  # id -> {name, team}
                for team_name, team_info in teams.items():
                    for name, eid in team_info.get("leader", {}).items():
                        all_members[eid] = {"name": name, "team": team_name}
                    for name, eid in team_info.get("members", {}).items():
                        all_members[eid] = {"name": name, "team": team_name}

                # Match with chat data
                chat_user_ids = set(chat.get("user_id", "") for chat in filtered_chats)
                active_member_ids = set()
                member_chat_counts = {}
                for chat in filtered_chats:
                    uid = chat.get("user_id", "")
                    if uid in all_members:
                        active_member_ids.add(uid)
                        member_chat_counts[uid] = member_chat_counts.get(uid, 0) + 1

                total_members = len(all_members)
                used_members = len(active_member_ids)
                usage_rate = (used_members / total_members * 100) if total_members > 0 else 0

                # Overall metrics
                m_col1, m_col2, m_col3 = st.columns(3)
                with m_col1:
                    st.metric("总客户经理数", total_members)
                with m_col2:
                    st.metric("已使用系统", used_members)
                with m_col3:
                    st.metric("使用率", f"{usage_rate:.1f}%")

                st.divider()

                # Team breakdown
                team_stats = []
                for team_name, team_info in teams.items():
                    team_member_ids = set()
                    for eid in team_info.get("leader", {}).values():
                        team_member_ids.add(eid)
                    for eid in team_info.get("members", {}).values():
                        team_member_ids.add(eid)
                    team_total = len(team_member_ids)
                    team_active = len(team_member_ids & active_member_ids)
                    team_chats = sum(member_chat_counts.get(mid, 0) for mid in team_member_ids)
                    team_stats.append({
                        "团队": team_name,
                        "总人数": team_total,
                        "已使用": team_active,
                        "使用率": round(team_active / team_total * 100, 1) if team_total > 0 else 0,
                        "对话数": team_chats
                    })

                df_teams = pd.DataFrame(team_stats)
                # Bar chart - usage rate by team
                chart_rate = alt.Chart(df_teams).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X("团队:N", sort="-y", axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("使用率:Q", title="使用率 (%)"),
                    color=alt.Color("使用率:Q", scale=alt.Scale(scheme="greens"), legend=None),
                    tooltip=["团队", "总人数", "已使用", "使用率", "对话数"]
                ).properties(height=300, title="各团队使用率")
                st.altair_chart(chart_rate, use_container_width=True)

                # Detailed table
                st.markdown("##### 各团队明细")
                st.dataframe(df_teams.sort_values("使用率", ascending=False), use_container_width=True, hide_index=True)

                # Unused members list
                unused_ids = set(all_members.keys()) - active_member_ids
                if unused_ids:
                    with st.expander(f" 未使用系统的成员（{len(unused_ids)} 人）", expanded=False):
                        unused_data = []
                        for uid in unused_ids:
                            info = all_members[uid]
                            unused_data.append({"工号": uid, "姓名": info["name"], "团队": info["team"]})
                        df_unused = pd.DataFrame(unused_data).sort_values("团队")
                        st.dataframe(df_unused, use_container_width=True, hide_index=True)
            else:
                st.info("未找到团队配置数据")
        

    except Exception as e:
        st.error(f"Error loading data: {e}")
