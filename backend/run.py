#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
应用启动入口
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_root = Path(__file__).resolve().parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import uvicorn
from app.core.settings import settings


def main():
    """启动应用"""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(settings.PORT or 8002),
        reload=True,
    )


if __name__ == "__main__":
    main()
