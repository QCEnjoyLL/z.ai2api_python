#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试工具调用修复
验证 Write 工具是否能正确添加 file_path 参数
"""

import asyncio
import json
import httpx
from datetime import datetime

# 配置
API_URL = "http://localhost:8080/v1/chat/completions"
API_KEY = "sk-your-api-key"  # 替换为你的 API Key

async def test_write_tool():
    """测试 Write 工具调用"""
    print(f"\n{datetime.now().strftime('%H:%M:%S')} 开始测试 Write 工具调用...")

    # 测试消息
    test_message = "创建一个a.html文件，内容是一个简单的HTML页面，包含标题Hello World"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    request_data = {
        "model": "GLM-4.5",
        "messages": [
            {
                "role": "user",
                "content": test_message
            }
        ],
        "stream": True,
        "tools": [{
            "type": "function",
            "function": {
                "name": "Write",
                "description": "写入文件到本地文件系统",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径"
                        },
                        "content": {
                            "type": "string",
                            "description": "文件内容"
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }
        }]
    }

    print(f"📤 发送请求: {test_message}")
    print(f"🔧 启用工具: Write")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                API_URL,
                headers=headers,
                json=request_data,
                timeout=60.0
            )

            print(f"📥 响应状态: {response.status_code}")

            if response.status_code == 200:
                print(f"\n⏳ 处理流式响应...")
                print("-" * 50)

                tool_calls_found = []
                content_buffer = ""

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            print("\n✅ 流结束")
                            break

                        try:
                            chunk = json.loads(data_str)

                            # 检查是否有工具调用
                            if "choices" in chunk and chunk["choices"]:
                                delta = chunk["choices"][0].get("delta", {})

                                # 收集文本内容
                                if "content" in delta and delta["content"]:
                                    content_buffer += delta["content"]

                                # 收集工具调用
                                if "tool_calls" in delta:
                                    for tool_call in delta["tool_calls"]:
                                        if "function" in tool_call:
                                            func = tool_call["function"]

                                            # 检查是否是新的工具调用
                                            if "name" in func:
                                                tool_calls_found.append({
                                                    "id": tool_call.get("id", ""),
                                                    "name": func["name"],
                                                    "arguments": ""
                                                })
                                                print(f"\n🔧 检测到工具调用: {func['name']}")

                                            # 累积参数
                                            if "arguments" in func and func["arguments"]:
                                                if tool_calls_found:
                                                    tool_calls_found[-1]["arguments"] += func["arguments"]

                                # 检查完成原因
                                if "finish_reason" in chunk["choices"][0]:
                                    finish = chunk["choices"][0]["finish_reason"]
                                    if finish == "tool_calls":
                                        print(f"🏁 工具调用完成")

                        except json.JSONDecodeError:
                            continue

                print("-" * 50)

                # 分析结果
                print("\n📊 分析结果:")

                if content_buffer:
                    print(f"\n📝 模型输出内容:")
                    print(content_buffer)

                if tool_calls_found:
                    print(f"\n🔧 发现 {len(tool_calls_found)} 个工具调用:")
                    for i, tool in enumerate(tool_calls_found, 1):
                        print(f"\n  [{i}] {tool['name']} (ID: {tool['id']})")

                        # 解析参数
                        try:
                            args = json.loads(tool["arguments"])
                            print(f"      参数:")
                            for key, value in args.items():
                                if key == "content":
                                    # 内容太长，只显示前100个字符
                                    display_value = value[:100] + "..." if len(value) > 100 else value
                                    print(f"        - {key}: {display_value}")
                                else:
                                    print(f"        - {key}: {value}")

                            # 检查关键参数
                            if tool['name'] == 'Write':
                                if 'file_path' in args:
                                    print(f"      ✅ file_path 参数存在: {args['file_path']}")
                                else:
                                    print(f"      ❌ file_path 参数缺失!")

                                if 'content' in args:
                                    print(f"      ✅ content 参数存在")
                                else:
                                    print(f"      ❌ content 参数缺失!")

                        except json.JSONDecodeError as e:
                            print(f"      ❌ 参数解析失败: {e}")
                            print(f"      原始参数: {tool['arguments'][:200]}...")
                else:
                    print("❌ 未检测到工具调用")

            else:
                print(f"❌ 请求失败: {response.text}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函数"""
    print("=" * 60)
    print("🔬 Z.AI 工具调用修复测试")
    print("=" * 60)

    print("\n测试说明:")
    print("1. 确保 z.ai2api_python 服务运行在 localhost:8080")
    print("2. 确保已应用最新的修复")
    print("3. 测试会发送创建文件的请求，验证 file_path 参数是否自动添加")

    await test_write_tool()

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())