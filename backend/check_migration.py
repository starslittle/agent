#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移验证脚本
检查所有必要的文件和目录是否存在
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_root = Path(__file__).resolve().parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


def check_migration():
    """检查迁移状态"""
    print("=" * 60)
    print("迁移验证检查")
    print("=" * 60)

    all_good = True

    # 检查关键目录
    required_dirs = [
        "app",
        "app/api",
        "app/core",
        "graph",
        "graph/nodes",
        "agent",
        "agent/tools",
        "agent/prompts",
        "agent/policies",
        "rag",
        "rag/engines",
        "rag/retrievers",
        "rag/pipelines",
        "infra",
        "infra/db",
        "infra/cache",
        "infra/storage",
        "infra/logging",
        "workers",
        "tests",
        "tests/unit",
        "tests/integration",
    ]

    print("\n检查目录结构...")
    for dir_path in required_dirs:
        full_path = backend_root / dir_path
        if full_path.exists():
            print(f"✅ {dir_path}")
        else:
            print(f"❌ {dir_path} - 不存在")
            all_good = False

    # 检查关键文件
    required_files = [
        "app/main.py",
        "app/deps.py",
        "app/core/settings.py",
        "app/api/agent_factory.py",
        "app/api/intent_router.py",
        "graph/state.py",
        "graph/builder.py",
        "graph/nodes/router.py",
        "graph/nodes/retrieval.py",
        "graph/nodes/tools.py",
        "graph/nodes/generation.py",
        "agent/tools/__init__.py",
        "infra/db/connection.py",
        "infra/cache/redis_client.py",
        "infra/storage/local_storage.py",
        "infra/logging/logger.py",
        "run.py",
    ]

    print("\n检查关键文件...")
    for file_path in required_files:
        full_path = backend_root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - 不存在")
            all_good = False

    # 检查配置文件
    config_files = [
        "configs/agents.yaml",
        "configs/rag.yaml",
    ]

    print("\n检查配置文件...")
    for file_path in config_files:
        full_path = backend_root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"⚠️  {file_path} - 不存在（可选）")

    # 检查 requirements
    req_files = [
        "requirements/base.txt",
        "requirements/api.txt",
        "requirements/database.txt",
        "requirements/cache.txt",
        "requirements/dev.txt",
    ]

    print("\n检查依赖文件...")
    for file_path in req_files:
        full_path = backend_root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - 不存在")
            all_good = False

    # 尝试导入关键模块
    print("\n检查模块导入...")
    try:
        sys.path.insert(0, str(backend_root))
        from app.core.settings import settings
        print("✅ app.core.settings")
    except Exception as e:
        print(f"❌ app.core.settings - {e}")
        all_good = False

    try:
        from app.api.agent_factory import create_agent_from_config
        print("✅ app.api.agent_factory")
    except Exception as e:
        print(f"❌ app.api.agent_factory - {e}")
        all_good = False

    try:
        from agent.tools import get_current_date
        print("✅ agent.tools")
    except Exception as e:
        print(f"❌ agent.tools - {e}")
        all_good = False

    # 最终结果
    print("\n" + "=" * 60)
    if all_good:
        print("✅ 迁移验证通过！")
        print("=" * 60)
        print("\n下一步：")
        print("1. 运行: python run.py")
        print("2. 访问: http://localhost:8002/docs")
        print("3. 测试 API 接口")
        return 0
    else:
        print("❌ 迁移验证失败，请检查上述错误")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(check_migration())
