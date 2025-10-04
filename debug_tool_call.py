#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试工具调用问题的测试脚本
"""

import asyncio
import json
import httpx
from typing import AsyncGenerator

async def test_tool_call():
    """测试工具调用"""

    # 配置
    API_URL = "http://localhost:8080/v1/chat/completions"
    API_KEY = "sk-your-api-key"  # 替换为你的 AUTH_TOKEN

    # 构造包含工具的请求
    request_data = {
        "model": "GLM-4.6",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "创建一个 test.html 文件，内容是简单的HTML页面"}
        ],
        "stream": True,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "create_file",
                    "description": "Create a file with the given content",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "The name of the file to create"
                            },
                            "content": {
                                "type": "string",
                                "description": "The content of the file"
                            }
                        },
                        "required": ["filename", "content"]
                    }
                }
            }
        ]
    }

    print("🚀 发送请求到 z.ai2api_python...")
    print(f"📝 模型: {request_data['model']}")
    print(f"🔧 工具数: {len(request_data.get('tools', []))}")
    print()

    # 发送请求
    async with httpx.AsyncClient() as client:
        response = await client.post(
            API_URL,
            json=request_data,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=60.0
        )

        print(f"📡 响应状态: {response.status_code}")
        print()

        if response.status_code != 200:
            print(f"❌ 错误响应: {response.text}")
            return

        # 处理流式响应
        print("📥 接收流式响应:")
        print("-" * 80)

        chunk_count = 0
        tool_call_detected = False
        finish_reason_detected = False
        done_detected = False

        async for line in response.aiter_lines():
            if not line:
                continue

            if line.startswith("data: "):
                chunk_count += 1
                data_str = line[6:]

                # 打印原始数据（限制长度）
                display_str = data_str[:200] + "..." if len(data_str) > 200 else data_str
                print(f"块 #{chunk_count}: {display_str}")

                if data_str == "[DONE]":
                    done_detected = True
                    print("  ✅ 检测到流结束标记 [DONE]")
                    break

                try:
                    data = json.loads(data_str)

                    # 检测工具调用
                    if "choices" in data and data["choices"]:
                        choice = data["choices"][0]

                        # 检测工具调用
                        if "delta" in choice and "tool_calls" in choice["delta"]:
                            tool_call_detected = True
                            tool_calls = choice["delta"]["tool_calls"]
                            print(f"  🔧 工具调用: {tool_calls}")

                        # 检测 finish_reason
                        if "finish_reason" in choice and choice["finish_reason"]:
                            finish_reason_detected = True
                            print(f"  🏁 finish_reason: {choice['finish_reason']}")

                        # 检测内容
                        if "delta" in choice and "content" in choice["delta"]:
                            content = choice["delta"]["content"]
                            if content:
                                print(f"  💬 内容: {content[:100]}...")

                except json.JSONDecodeError:
                    print(f"  ⚠️ 无法解析 JSON")

        print("-" * 80)
        print()
        print("📊 统计:")
        print(f"  总块数: {chunk_count}")
        print(f"  工具调用检测: {'✅' if tool_call_detected else '❌'}")
        print(f"  finish_reason 检测: {'✅' if finish_reason_detected else '❌'}")
        print(f"  [DONE] 检测: {'✅' if done_detected else '❌'}")

        if tool_call_detected and finish_reason_detected and done_detected:
            print("\n✅ 工具调用响应格式正确！")
        else:
            print("\n❌ 工具调用响应格式有问题！")
            if not finish_reason_detected:
                print("  - 缺少 finish_reason")
            if not done_detected:
                print("  - 缺少 [DONE] 结束标记")

if __name__ == "__main__":
    asyncio.run(test_tool_call())