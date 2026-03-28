#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理迁移后不再使用的文件和目录
"""

import os
import shutil
from pathlib import Path


def cleanup_backend():
    """清理backend目录中的旧文件"""

    backend_root = Path(__file__).resolve().parent

    print("=" * 60)
    print("清理迁移后的旧文件")
    print("=" * 60)

    # 要删除的目录
    dirs_to_remove = [
        backend_root / "src",              # 旧的源代码目录
        backend_root / "prompts",          # 旧的prompts目录（已迁移到agent/prompts）
    ]

    # 要清理的__pycache__目录
    pycache_dirs = list(backend_root.rglob("__pycache__"))

    # 要删除的旧文件
    files_to_remove = [
        backend_root / "test_agent.py",   # 如果存在旧的测试文件
    ]

    # 询问确认
    print("\n将要删除以下目录：")
    for d in dirs_to_remove:
        if d.exists():
            print(f"  - {d}")

    print(f"\n将要清理 {len(pycache_dirs)} 个 __pycache__ 目录")

    # 删除目录
    for dir_path in dirs_to_remove:
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                print(f"✅ 已删除: {dir_path}")
            except Exception as e:
                print(f"❌ 删除失败 {dir_path}: {e}")

    # 清理__pycache__
    for pycache_dir in pycache_dirs:
        try:
            shutil.rmtree(pycache_dir)
        except Exception:
            pass
    print(f"✅ 已清理 {len(pycache_dirs)} 个 __pycache__ 目录")

    # 删除文件
    for file_path in files_to_remove:
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"✅ 已删除: {file_path}")
            except Exception as e:
                print(f"⚠️  跳过: {file_path}")

    print("\n" + "=" * 60)
    print("清理完成！")
    print("=" * 60)

    # 显示当前目录结构
    print("\n当前主要目录：")
    main_dirs = [
        "app", "agent", "graph", "rag", "infra",
        "workers", "configs", "scripts", "tests", "requirements"
    ]
    for d in main_dirs:
        dir_path = backend_root / d
        if dir_path.exists():
            print(f"  ✅ {d}/")
        else:
            print(f"  ❌ {d}/ (缺失)")


if __name__ == "__main__":
    import sys

    print("⚠️  警告：此操作将删除以下内容：")
    print("  - backend/src/ (旧代码目录)")
    print("  - backend/prompts/ (旧prompts目录)")
    print("  - 所有 __pycache__ 目录")
    print("  - backend/test_agent.py (如果存在)")
    print()

    confirm = input("确认删除？(yes/no): ").strip().lower()

    if confirm in ["yes", "y"]:
        cleanup_backend()
    else:
        print("已取消清理")
        sys.exit(0)
