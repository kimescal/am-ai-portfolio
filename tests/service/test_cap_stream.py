#!/usr/bin/env python3
"""
测试 /cap_stream 接口的脚本
运行方式：python test_cap_stream.py
"""

import asyncio
import httpx
import json
import re
from datetime import datetime
from pathlib import Path


# ==================== 配置 ====================
BASE_URL = "http://localhost:8080"  # 修改为你的服务地址
API_ENDPOINT = "/cap_stream"
SHOW_RAW_DATA = False  # 是否显示原始JSON数据（调试用）
STREAM_OUTPUT = True  # 是否实时流式显示文本输出
DETECT_DUPLICATES = True  # 是否检测重复输出
ENABLE_LOGGING = True  # 是否启用日志文件
LOG_DIR = Path("test_logs")  # 日志文件目录

# 全局日志文件句柄
_log_file = None


# ==================== 测试数据 ====================
TEST_QUERIES = [
    "帮我查询民生理财上半年的需求情况",
    "计算 123 + 456",
    "搜索最新的 Python 新闻",
]


# ==================== 颜色输出（可选） ====================
class Colors:
    """终端颜色代码"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def remove_color_codes(text: str) -> str:
    """移除ANSI颜色代码"""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


def log_to_file(text: str, end: str = '\n'):
    """写入日志文件"""
    global _log_file
    if _log_file and ENABLE_LOGGING:
        try:
            clean_text = remove_color_codes(text)
            _log_file.write(clean_text + end)
            _log_file.flush()
        except Exception as e:
            print(f"日志写入失败: {e}")


def print_colored(text: str, color: str = Colors.ENDC, end: str = '\n', flush: bool = False):
    """打印带颜色的文本，并同时写入日志文件"""
    print(f"{color}{text}{Colors.ENDC}", end=end, flush=flush)
    log_to_file(text, end)


def init_log_file(query: str = "") -> Path | None:
    """初始化日志文件"""
    global _log_file
    
    if not ENABLE_LOGGING:
        return None
    
    try:
        # 创建日志目录
        LOG_DIR.mkdir(exist_ok=True)
        
        # 生成日志文件名（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_slug = re.sub(r'[^\w\s-]', '', query)[:20].strip().replace(' ', '_')
        if query_slug:
            filename = f"test_{timestamp}_{query_slug}.log"
        else:
            filename = f"test_{timestamp}.log"
        
        log_path = LOG_DIR / filename
        
        # 打开日志文件
        _log_file = open(log_path, 'w', encoding='utf-8')
        
        # 写入文件头
        _log_file.write("="*80 + "\n")
        _log_file.write(f"CAP Stream API 测试日志\n")
        _log_file.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        _log_file.write(f"查询: {query or '(无)'}\n")
        _log_file.write(f"URL: {BASE_URL}{API_ENDPOINT}\n")
        _log_file.write("="*80 + "\n\n")
        _log_file.flush()
        
        return log_path
    except Exception as e:
        print(f"❌ 创建日志文件失败: {e}")
        return None


def close_log_file(log_path: Path | None = None):
    """关闭日志文件"""
    global _log_file
    
    if _log_file:
        try:
            _log_file.write("\n" + "="*80 + "\n")
            _log_file.write(f"测试结束: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            _log_file.write("="*80 + "\n")
            _log_file.close()
            _log_file = None
            
            if log_path and log_path.exists():
                print_colored(f"\n📝 日志已保存到: {log_path.absolute()}", Colors.CYAN)
                print_colored(f"   文件大小: {log_path.stat().st_size / 1024:.2f} KB", Colors.CYAN)
        except Exception as e:
            print(f"❌ 关闭日志文件失败: {e}")


# ==================== SSE 流解析 ====================
async def parse_sse_stream(response):
    """解析 Server-Sent Events 流"""
    buffer = ""
    
    async for chunk in response.aiter_bytes():
        buffer += chunk.decode('utf-8')
        
        # 处理缓冲区中的完整事件
        while '\n\n' in buffer:
            event, buffer = buffer.split('\n\n', 1)
            
            # 解析事件
            if event.startswith('data: '):
                data_str = event[6:]  # 去掉 "data: " 前缀
                
                if data_str == '[DONE]':
                    print_colored("\n✅ 流结束", Colors.GREEN)
                    return
                
                try:
                    data = json.loads(data_str)
                    yield data
                except json.JSONDecodeError as e:
                    print_colored(f"❌ JSON 解析错误: {e}", Colors.RED)
                    print(f"原始数据: {data_str}")


# ==================== 主测试函数 ====================
async def test_stream_api(query: str):
    """测试流式 API"""
    
    # 初始化日志文件
    log_path = init_log_file(query)
    if log_path and ENABLE_LOGGING:
        print(f"📝 日志文件: {log_path.name}")
    
    print_colored("\n" + "="*80, Colors.HEADER)
    print_colored(f"📝 测试查询: {query}", Colors.BOLD)
    print_colored("="*80, Colors.HEADER)
    
    # 构造请求数据（根据你的实际格式）
    payload = {
        "messages": [],
        "question_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": [
            {
                "type": "text",
                "value": query
            }
        ],
        "session_id": "001"  # 使用时间戳作为 session_id
    }
    
    print_colored(f"\n📤 发送请求到: {BASE_URL}{API_ENDPOINT}", Colors.CYAN)
    print_colored(f"请求数据: {json.dumps(payload, ensure_ascii=False, indent=2)}", Colors.CYAN)
    
    start_time = datetime.now()
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{BASE_URL}{API_ENDPOINT}",
                json=payload,
            ) as response:
                
                if response.status_code != 200:
                    print_colored(f"\n❌ 错误: HTTP {response.status_code}", Colors.RED)
                    error_text = await response.aread()
                    print(error_text.decode('utf-8'))
                    close_log_file(log_path)
                    return
                
                print_colored("\n📥 接收响应流:", Colors.GREEN)
                print_colored("-" * 80, Colors.GREEN)
                
                event_count = 0
                tool_calls = []
                accumulated_text = ""  # 累积显示的文本
                stream_started = False  # 是否已开始流式输出
                
                # 重复检测相关
                seen_contents = []  # 所有已见过的文本内容
                duplicate_count = 0  # 重复内容计数
                duplicate_details = []  # 重复内容详情
                
                # 解析 SSE 流
                async for data in parse_sse_stream(response):
                    event_count += 1
                    
                    # 显示原始数据（调试用）
                    if SHOW_RAW_DATA:
                        print_colored(f"\n[原始数据 {event_count}]", Colors.YELLOW)
                        print(json.dumps(data, ensure_ascii=False, indent=2))
                        print_colored("-" * 60, Colors.YELLOW)
                    
                    # 提取信息
                    answer = data.get("answer", {})
                    session_id = data.get("session_id", "")
                    
                    finish_reason = answer.get("finish_reason", "")
                    step = answer.get("step", {})
                    content = answer.get("content", [])
                    
                    step_label = step.get("label", "")
                    step_state = step.get("state", "")
                    
                    # 打印事件信息
                    print_colored(f"\n[事件 {event_count}]", Colors.YELLOW)
                    print(f"  步骤状态: {step_state}")
                    print(f"  步骤标签: {step_label}")
                    if finish_reason:
                        print(f"  完成原因: {finish_reason}")
                    
                    # 打印内容
                    if content:
                        print_colored(f"  📝 内容 ({len(content)} 项):", Colors.CYAN)
                        for idx, item in enumerate(content, 1):
                            content_type = item.get("type", "")
                            content_value = item.get("value", "")
                            
                            print(f"    [{idx}] 类型: {content_type}")
                            
                            if content_type == "text" and content_value:
                                # 检查是否是工具调用
                                if "工具调用" in content_value or "🛠️" in content_value or "tool" in content_value.lower():
                                    print_colored(f"        🛠️  {content_value.strip()}", Colors.CYAN)
                                    tool_calls.append(content_value)
                                else:
                                    # 重复检测
                                    is_duplicate = False
                                    if DETECT_DUPLICATES and content_value.strip():
                                        # 检查是否与之前的内容完全相同
                                        for seen_idx, seen_content in enumerate(seen_contents):
                                            if content_value.strip() == seen_content.strip():
                                                is_duplicate = True
                                                duplicate_count += 1
                                                duplicate_details.append({
                                                    "event": event_count,
                                                    "content": content_value[:50] + "..." if len(content_value) > 50 else content_value,
                                                    "first_seen_event": seen_idx + 1,
                                                })
                                                print_colored(f"        ⚠️  [重复内容 #{duplicate_count}] (首次出现在事件 #{seen_idx + 1})", Colors.RED)
                                                break
                                        
                                        if not is_duplicate:
                                            seen_contents.append(content_value)
                                    
                                    # 累积文本内容
                                    accumulated_text += content_value
                                    
                                    # 实时流式输出
                                    if STREAM_OUTPUT and content_value.strip():
                                        if not stream_started:
                                            print_colored("\n💬 实时输出:", Colors.BOLD)
                                            print_colored("-" * 80, Colors.BLUE)
                                            stream_started = True
                                        
                                        # 如果是重复内容，用红色显示
                                        if is_duplicate:
                                            print_colored(content_value, Colors.RED, end='', flush=True)
                                        else:
                                            print(content_value, end='', flush=True)
                                    
                                    # 在事件详情中显示
                                    if not STREAM_OUTPUT:
                                        if is_duplicate:
                                            print_colored(f"        值: {content_value} [重复]", Colors.RED)
                                        else:
                                            print(f"        值: {content_value}")
                            elif content_value:
                                # 显示其他类型的内容
                                value_preview = str(content_value)[:100]
                                if len(str(content_value)) > 100:
                                    value_preview += "..."
                                print(f"        值: {value_preview}")
                    
                    # 如果没有内容但有其他字段
                    if not content and answer:
                        other_fields = {k: v for k, v in answer.items() if k not in ["finish_reason", "step", "content"]}
                        if other_fields:
                            print(f"  其他字段: {json.dumps(other_fields, ensure_ascii=False)}")
                
                # 如果有流式输出，添加结束标记
                if stream_started:
                    print()  # 换行
                    print_colored("-" * 80, Colors.BLUE)
                
                # 统计信息
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                print_colored("\n" + "=" * 80, Colors.GREEN)
                print_colored("📊 统计信息:", Colors.BOLD)
                print(f"  总事件数: {event_count}")
                print(f"  工具调用数: {len(tool_calls)}")
                print(f"  耗时: {duration:.2f} 秒")
                print(f"  Session ID: {session_id}")
                
                # 重复检测结果
                if DETECT_DUPLICATES:
                    if duplicate_count > 0:
                        print_colored(f"\n⚠️  重复检测结果:", Colors.RED + Colors.BOLD)
                        print_colored(f"  发现 {duplicate_count} 处重复内容！", Colors.RED)
                        print(f"  唯一内容块数: {len(seen_contents)}")
                        print(f"  总内容块数: {len(seen_contents) + duplicate_count}")
                        
                        if duplicate_details:
                            print_colored("\n  重复详情:", Colors.YELLOW)
                            for i, dup in enumerate(duplicate_details[:10], 1):  # 最多显示10个
                                print(f"    {i}. 事件 #{dup['event']} 重复了事件 #{dup['first_seen_event']} 的内容")
                                print(f"       内容: {dup['content']}")
                            if len(duplicate_details) > 10:
                                print(f"    ... 还有 {len(duplicate_details) - 10} 个重复")
                    else:
                        print_colored(f"  ✅ 未发现重复内容", Colors.GREEN)
                
                # 显示完整的累积文本输出
                if accumulated_text:
                    print_colored("\n📄 完整文本输出:", Colors.BOLD)
                    print_colored("-" * 80, Colors.CYAN)
                    print(accumulated_text)
                    print_colored("-" * 80, Colors.CYAN)
                    print(f"  文本长度: {len(accumulated_text)} 字符")
                
                if tool_calls:
                    print_colored("\n🛠️ 工具调用列表:", Colors.CYAN)
                    for i, tc in enumerate(tool_calls, 1):
                        print(f"  {i}. {tc.strip()}")
                
                # 关闭日志文件
                close_log_file(log_path)
    
    except httpx.ConnectError:
        print_colored(f"\n❌ 连接错误: 无法连接到 {BASE_URL}", Colors.RED)
        print_colored("请确保服务正在运行！", Colors.YELLOW)
        close_log_file(log_path)
    except httpx.TimeoutException:
        print_colored("\n❌ 请求超时", Colors.RED)
        close_log_file(log_path)
    except Exception as e:
        print_colored(f"\n❌ 未知错误: {e}", Colors.RED)
        import traceback
        traceback.print_exc()
        close_log_file(log_path)


# ==================== 交互式测试 ====================
async def interactive_test():
    """交互式测试模式"""
    global SHOW_RAW_DATA, STREAM_OUTPUT, DETECT_DUPLICATES, ENABLE_LOGGING
    
    print_colored("\n" + "="*80, Colors.HEADER)
    print_colored("🧪 CAP Stream API 测试工具", Colors.BOLD)
    print_colored("="*80, Colors.HEADER)
    
    if ENABLE_LOGGING:
        print_colored(f"📁 日志目录: {LOG_DIR.absolute()}", Colors.CYAN)
    
    while True:
        print_colored("\n选择测试模式:", Colors.CYAN)
        print("1. 使用预设查询")
        print("2. 输入自定义查询")
        print("3. 运行所有预设查询")
        print(f"4. 切换原始数据显示 (当前: {'开' if SHOW_RAW_DATA else '关'})")
        print(f"5. 切换实时流式输出 (当前: {'开' if STREAM_OUTPUT else '关'})")
        print(f"6. 切换重复检测 (当前: {'开' if DETECT_DUPLICATES else '关'})")
        print(f"7. 切换日志记录 (当前: {'开' if ENABLE_LOGGING else '关'})")
        print("8. 退出")
        
        choice = input("\n请选择 (1-8): ").strip()
        
        if choice == "1":
            print_colored("\n预设查询列表:", Colors.CYAN)
            for i, query in enumerate(TEST_QUERIES, 1):
                print(f"{i}. {query}")
            
            query_num = input("\n选择查询 (1-{}): ".format(len(TEST_QUERIES))).strip()
            try:
                idx = int(query_num) - 1
                if 0 <= idx < len(TEST_QUERIES):
                    await test_stream_api(TEST_QUERIES[idx])
                else:
                    print_colored("❌ 无效的选择", Colors.RED)
            except ValueError:
                print_colored("❌ 请输入数字", Colors.RED)
        
        elif choice == "2":
            query = input("\n请输入查询内容: ").strip()
            if query:
                await test_stream_api(query)
            else:
                print_colored("❌ 查询不能为空", Colors.RED)
        
        elif choice == "3":
            for query in TEST_QUERIES:
                await test_stream_api(query)
                await asyncio.sleep(1)  # 间隔1秒
        
        elif choice == "4":
            SHOW_RAW_DATA = not SHOW_RAW_DATA
            status = "开启" if SHOW_RAW_DATA else "关闭"
            print_colored(f"\n✅ 原始数据显示已{status}", Colors.GREEN)
        
        elif choice == "5":
            STREAM_OUTPUT = not STREAM_OUTPUT
            status = "开启" if STREAM_OUTPUT else "关闭"
            print_colored(f"\n✅ 实时流式输出已{status}", Colors.GREEN)
        
        elif choice == "6":
            DETECT_DUPLICATES = not DETECT_DUPLICATES
            status = "开启" if DETECT_DUPLICATES else "关闭"
            print_colored(f"\n✅ 重复检测已{status}", Colors.GREEN)
        
        elif choice == "7":
            print_colored("\n👋 再见!", Colors.GREEN)
            break
        
        else:
            print_colored("❌ 无效的选择，请输入 1-7", Colors.RED)


# ==================== 快速测试 ====================
async def quick_test():
    """快速测试第一个查询"""
    print_colored("🚀 快速测试模式", Colors.BOLD)
    await test_stream_api(TEST_QUERIES[0])


# ==================== 主入口 ====================
async def main():
    """主函数"""
    import sys
    global SHOW_RAW_DATA, STREAM_OUTPUT, DETECT_DUPLICATES
    
    # 检查是否有 --verbose 或 -v 参数
    if "--verbose" in sys.argv or "-v" in sys.argv:
        SHOW_RAW_DATA = True
        if "--verbose" in sys.argv:
            sys.argv.remove("--verbose")
        if "-v" in sys.argv:
            sys.argv.remove("-v")
        print_colored("🔍 已启用详细输出模式（显示原始JSON数据）", Colors.YELLOW)
    
    # 检查是否有 --no-stream 参数
    if "--no-stream" in sys.argv:
        STREAM_OUTPUT = False
        sys.argv.remove("--no-stream")
        print_colored("📋 已禁用实时流式输出", Colors.YELLOW)
    
    # 检查是否有 --no-duplicate-check 参数
    if "--no-duplicate-check" in sys.argv:
        DETECT_DUPLICATES = False
        sys.argv.remove("--no-duplicate-check")
        print_colored("🔕 已禁用重复检测", Colors.YELLOW)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--quick":
            await quick_test()
        elif sys.argv[1] == "--all":
            for query in TEST_QUERIES:
                await test_stream_api(query)
                await asyncio.sleep(1)
        elif sys.argv[1] == "--query":
            if len(sys.argv) > 2:
                await test_stream_api(" ".join(sys.argv[2:]))
            else:
                print_colored("❌ 请提供查询内容", Colors.RED)
        else:
            print_colored("用法:", Colors.CYAN)
            print("  python test_cap_stream.py                          # 交互式模式")
            print("  python test_cap_stream.py --quick                  # 快速测试")
            print("  python test_cap_stream.py --all                    # 测试所有预设查询")
            print("  python test_cap_stream.py --query 你的查询          # 测试自定义查询")
            print("\n选项:")
            print("  --verbose 或 -v        显示原始JSON数据（调试用）")
            print("  --no-stream            禁用实时流式输出，仅在最后显示完整结果")
            print("  --no-duplicate-check   禁用重复检测")
            print("\n示例:")
            print("  python test_cap_stream.py --quick --verbose            # 快速测试 + 详细输出")
            print("  python test_cap_stream.py --query 你好 --no-stream     # 自定义查询 + 不实时显示")
            print("  python test_cap_stream.py --all --no-duplicate-check  # 测试所有查询 + 不检测重复")
    else:
        await interactive_test()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_colored("\n\n👋 测试中断", Colors.YELLOW)

