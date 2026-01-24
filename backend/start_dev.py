#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速启动脚本 - 正确加载环境变量并启动服务
"""

import os
import sys
from pathlib import Path

# 确保在backend目录
backend_root = Path(__file__).resolve().parent
os.chdir(backend_root)

# 添加到Python路径
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

print(f"工作目录: {os.getcwd()}")
print(f"Python路径已添加: {backend_root}")

# 检查.env文件
env_file = backend_root / ".env"
if not env_file.exists():
    print(f"⚠️  警告: .env文件不存在于 {env_file}")
    print("请确保已配置环境变量")
else:
    print(f"✅ .env文件已找到: {env_file}")

# 导入并运行
import uvicorn
from app.core.settings import settings

print(f"\n🚀 启动服务...")
print(f"端口: {settings.PORT or 8002}")
print(f"模式: {'开发模式' if settings.ENVIRONMENT == 'development' else '生产模式'}")
print(f"数据库: {'已配置' if settings.DATABASE_URL else '未配置'}")
print(f"Redis: {'已配置' if settings.REDIS_URL else '未配置'}")
print(f"API Key: {'已配置' if settings.DASHSCOPE_API_KEY else '未配置'}")
print()

if __name__ == "__main__":
    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=int(settings.PORT or 8002),
            reload=True,
        )
    except KeyboardInterrupt:
        print("\n\n👋 服务已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
