"""Pytest 配置文件"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


@pytest.fixture
def sample_query():
    """示例查询"""
    return "今天天气怎么样？"


@pytest.fixture
def sample_chat_history():
    """示例聊天历史"""
    return [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
    ]
