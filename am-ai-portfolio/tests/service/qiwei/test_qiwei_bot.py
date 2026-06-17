import pytest
import json
import sys
import os
from unittest.mock import AsyncMock, patch

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from service.qiwei.qiwei_bot import build_qiwei_stream_payload

# 测试工具函数而不是路由处理函数
@pytest.mark.asyncio
async def test_build_qiwei_stream_payload():
    """测试构建企业微信流式响应payload的函数"""

    # 测试未完成的流式响应
    payload = build_qiwei_stream_payload(
        stream_id="test-stream-123",
        full_text="这是测试回复",
        finished=False
    )

    assert isinstance(payload, dict)
    assert payload["msgtype"] == "stream"
    assert payload["stream"]["id"] == "test-stream-123"
    assert payload["stream"]["finish"] is False
    assert "这是测试回复" in payload["stream"]["content"]

    # 测试已完成的流式响应
    payload = build_qiwei_stream_payload(
        stream_id="test-stream-456",
        full_text="这是完整的测试回复",
        finished=True
    )

    assert payload["stream"]["finish"] is True
    assert "这是完整的测试回复" in payload["stream"]["content"]