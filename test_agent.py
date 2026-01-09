#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奇点AI Agent 测试脚本
用于检测后端服务和 Agent 是否正常运行
"""

import requests
import json
import sys

# 后端地址
BASE_URL = "http://localhost:8002"

def test_health():
    """测试健康检查接口"""
    print("=" * 60)
    print("【测试 1】健康检查 (/healthz)")
    print("=" * 60)
    try:
        response = requests.get(f"{BASE_URL}/healthz", timeout=5)
        print(f"✅ 状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 响应内容:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
            return True
        else:
            print(f"❌ 健康检查失败: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到后端服务，请确认后端是否启动在 http://localhost:8000")
        return False
    except Exception as e:
        print(f"❌ 健康检查出错: {e}")
        return False


def test_simple_query():
    """测试简单问答（非流式）"""
    print("\n" + "=" * 60)
    print("【测试 2】简单问答 (/query)")
    print("=" * 60)
    
    payload = {
        "query": "你好，请介绍一下你自己",
        "agent_name": "default"
    }
    
    print(f"📤 发送请求:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/query",
            json=payload,
            timeout=30
        )
        print(f"\n✅ 状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 使用的 Agent: {data.get('agent_name')}")
            print(f"✅ 回答内容:\n{data.get('answer', data.get('output'))}")
            return True
        else:
            print(f"❌ 请求失败: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时（30秒），后端可能卡住了")
        return False
    except Exception as e:
        print(f"❌ 请求出错: {e}")
        return False


def test_stream_query():
    """测试流式问答 (/query_stream)"""
    print("\n" + "=" * 60)
    print("【测试 3】流式问答 (/query_stream)")
    print("=" * 60)
    
    payload = {
        "query": "用一句话介绍人工智能",
        "agent_name": "default"
    }
    
    print(f"📤 发送流式请求:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/query_stream",
            json=payload,
            stream=True,
            timeout=30
        )
        
        print(f"\n✅ 状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ 收到流式响应，正在解析...\n")
            print("📥 实时输出: ", end="", flush=True)
            
            accumulated = ""
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if chunk.get("type") == "delta":
                        data = chunk.get("data", "")
                        print(data, end="", flush=True)
                        accumulated += data
                    elif chunk.get("type") == "done":
                        print("\n\n✅ 流式输出完成")
                        return True
                    elif chunk.get("type") == "error":
                        print(f"\n❌ 流式错误: {chunk.get('message')}")
                        return False
                except json.JSONDecodeError:
                    print(f"\n⚠️ 无法解析的行: {line}")
            
            if accumulated:
                return True
            else:
                print("\n⚠️ 流式响应未产生任何内容")
                return False
        else:
            print(f"❌ 流式请求失败: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ 流式请求超时（30秒）")
        return False
    except Exception as e:
        print(f"❌ 流式请求出错: {e}")
        return False


def main():
    print("\n" + "🚀" * 30)
    print("奇点AI Agent 测试脚本")
    print("🚀" * 30 + "\n")
    
    results = []
    
    # 执行测试
    results.append(("健康检查", test_health()))
    results.append(("简单问答", test_simple_query()))
    results.append(("流式问答", test_stream_query()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有测试通过！Agent 运行正常。")
        sys.exit(0)
    else:
        print("⚠️ 部分测试失败，请检查后端日志。")
        sys.exit(1)


if __name__ == "__main__":
    main()

