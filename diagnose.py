#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
综合诊断脚本 - 定位工具调用问题
"""

import asyncio
import json
import httpx
import sys
from typing import Dict, Any, List

# 配置
API_URL = "http://localhost:8080/v1/chat/completions"
API_KEY = "sk-your-api-key"  # 替换为你的 AUTH_TOKEN

# ANSI 颜色代码
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_colored(text: str, color: str = RESET):
    """打印带颜色的文本"""
    print(f"{color}{text}{RESET}")

def print_section(title: str):
    """打印分节标题"""
    print()
    print_colored(f"{'='*80}", CYAN)
    print_colored(f"  {title}", BOLD + CYAN)
    print_colored(f"{'='*80}", CYAN)
    print()

async def test_basic_connection():
    """测试基本连接"""
    print_section("1. 测试基本连接")

    try:
        async with httpx.AsyncClient() as client:
            # 测试模型列表
            response = await client.get(
                f"http://localhost:8080/v1/models",
                headers={"Authorization": f"Bearer {API_KEY}"}
            )

            if response.status_code == 200:
                models = response.json()
                print_colored("✅ 连接成功！", GREEN)
                print(f"可用模型数: {len(models.get('data', []))}")
                for model in models.get('data', [])[:5]:
                    print(f"  - {model.get('id')}")
                return True
            else:
                print_colored(f"❌ 连接失败: {response.status_code}", RED)
                return False
    except Exception as e:
        print_colored(f"❌ 连接错误: {e}", RED)
        return False

async def test_simple_chat():
    """测试简单对话（无工具）"""
    print_section("2. 测试简单对话（无工具）")

    request_data = {
        "model": "GLM-4.5",
        "messages": [
            {"role": "user", "content": "说'测试成功'"}
        ],
        "stream": False
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                API_URL,
                json=request_data,
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                print_colored("✅ 简单对话成功！", GREEN)
                print(f"回复: {content}")
                return True
            else:
                print_colored(f"❌ 请求失败: {response.status_code}", RED)
                return False
    except Exception as e:
        print_colored(f"❌ 错误: {e}", RED)
        return False

async def test_tool_call_response():
    """测试工具调用响应格式"""
    print_section("3. 测试工具调用响应格式")

    # Claude Code 使用的标准工具定义
    tools = [
        {
            "type": "function",
            "function": {
                "name": "str_replace_based_edit_tool",
                "description": "Create or edit a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["create", "str_replace"],
                            "description": "The command to execute"
                        },
                        "path": {
                            "type": "string",
                            "description": "The path of the file"
                        },
                        "file_text": {
                            "type": "string",
                            "description": "The content for create command"
                        },
                        "old_str": {
                            "type": "string",
                            "description": "The string to replace"
                        },
                        "new_str": {
                            "type": "string",
                            "description": "The new string"
                        }
                    },
                    "required": ["command", "path"]
                }
            }
        }
    ]

    request_data = {
        "model": "GLM-4.6",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "创建一个名为 test.html 的文件，内容是：<h1>Hello World</h1>"}
        ],
        "tools": tools,
        "stream": True
    }

    print(f"发送工具调用请求...")
    print(f"工具: {tools[0]['function']['name']}")
    print()

    tool_call_chunks = []
    finish_reason_found = False
    done_found = False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                API_URL,
                json=request_data,
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=60.0
            )

            if response.status_code != 200:
                print_colored(f"❌ 请求失败: {response.status_code}", RED)
                print(response.text)
                return False

            print_colored("📥 接收流式响应:", YELLOW)
            print("-" * 60)

            chunk_count = 0
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                chunk_count += 1
                data_str = line[6:]

                if data_str == "[DONE]":
                    done_found = True
                    print_colored(f"\n✅ [DONE] 标记检测到", GREEN)
                    break

                try:
                    data = json.loads(data_str)

                    # 检查工具调用
                    if "choices" in data and data["choices"]:
                        choice = data["choices"][0]
                        delta = choice.get("delta", {})

                        # 检测工具调用
                        if "tool_calls" in delta:
                            tool_call_chunks.append(data)
                            tool_calls = delta["tool_calls"]

                            # 打印工具调用信息
                            for tc in tool_calls:
                                if "function" in tc:
                                    func = tc["function"]
                                    if "name" in func:
                                        print_colored(f"\n🔧 工具名: {func['name']}", MAGENTA)
                                    if "arguments" in func and func["arguments"]:
                                        args = func["arguments"]
                                        print_colored(f"📝 参数片段: {args[:100]}...", BLUE)

                        # 检测 finish_reason
                        if "finish_reason" in choice and choice["finish_reason"]:
                            finish_reason_found = True
                            print_colored(f"\n🏁 finish_reason: {choice['finish_reason']}", YELLOW)

                        # 检测普通内容
                        if "content" in delta and delta["content"]:
                            print(f"💬 内容: {delta['content'][:50]}...")

                except json.JSONDecodeError as e:
                    print_colored(f"⚠️ JSON 解析错误: {e}", RED)

            print("-" * 60)
            print()

            # 分析结果
            print_colored("📊 分析结果:", BOLD)

            if tool_call_chunks:
                print_colored(f"✅ 检测到 {len(tool_call_chunks)} 个工具调用块", GREEN)

                # 尝试重建完整的工具调用
                print()
                print_colored("🔍 重建工具调用参数:", YELLOW)

                tool_name = None
                tool_id = None
                full_arguments = ""

                for chunk in tool_call_chunks:
                    delta = chunk["choices"][0]["delta"]
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            if "id" in tc:
                                tool_id = tc["id"]
                            if "function" in tc:
                                func = tc["function"]
                                if "name" in func:
                                    tool_name = func["name"]
                                if "arguments" in func:
                                    full_arguments += func["arguments"]

                print(f"  工具ID: {tool_id}")
                print(f"  工具名: {tool_name}")
                print(f"  参数长度: {len(full_arguments)}")

                # 尝试解析参数
                if full_arguments:
                    try:
                        # 尝试修复并解析 JSON
                        import json_repair
                        repaired = json_repair.repair_json(full_arguments)
                        args_obj = json.loads(repaired)

                        print_colored("\n✅ 参数解析成功:", GREEN)
                        print(json.dumps(args_obj, indent=2, ensure_ascii=False))

                        # 检查必需字段
                        print()
                        print_colored("🔍 检查必需字段:", YELLOW)

                        # 对于文件操作工具
                        if tool_name in ["str_replace_based_edit_tool", "create_file", "write_file"]:
                            has_path = "path" in args_obj or "file_path" in args_obj
                            has_content = "content" in args_obj or "file_text" in args_obj

                            if has_path:
                                print_colored("  ✅ 文件路径字段存在", GREEN)
                                path_field = "path" if "path" in args_obj else "file_path"
                                print(f"     {path_field}: {args_obj.get(path_field)}")
                            else:
                                print_colored("  ❌ 缺少文件路径字段！", RED)

                            if has_content:
                                print_colored("  ✅ 文件内容字段存在", GREEN)
                            else:
                                print_colored("  ⚠️ 缺少文件内容字段", YELLOW)

                    except Exception as e:
                        print_colored(f"\n❌ 参数解析失败: {e}", RED)
                        print(f"原始参数: {full_arguments[:200]}...")
            else:
                print_colored("❌ 未检测到工具调用块", RED)

            if finish_reason_found:
                print_colored("✅ finish_reason 存在", GREEN)
            else:
                print_colored("❌ 缺少 finish_reason", RED)

            if done_found:
                print_colored("✅ [DONE] 标记存在", GREEN)
            else:
                print_colored("❌ 缺少 [DONE] 标记", RED)

            return bool(tool_call_chunks)

    except Exception as e:
        print_colored(f"❌ 请求错误: {e}", RED)
        import traceback
        traceback.print_exc()
        return False

async def test_direct_zai_api():
    """直接测试 Z.AI API（绕过 z.ai2api_python）"""
    print_section("4. 直接测试 Z.AI API")

    print_colored("⚠️ 此测试需要有效的 Z.AI token", YELLOW)
    print("如果要测试，请修改脚本中的 Z_AI_TOKEN")

    # 这里需要一个有效的 Z.AI token
    # Z_AI_TOKEN = "your_zai_token_here"
    # 如果有 token，可以取消下面的注释进行测试

    """
    headers = {
        "Authorization": f"Bearer {Z_AI_TOKEN}",
        "Content-Type": "application/json"
    }

    # Z.AI 的原始请求格式
    request_data = {
        # Z.AI 特定的请求格式
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://chat.z.ai/api/chat/completions",
            json=request_data,
            headers=headers
        )
        # 分析 Z.AI 的原始响应
    """

    print("跳过（需要配置 Z.AI token）")
    return None

async def main():
    """运行所有诊断测试"""
    print_colored("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     z.ai2api_python 工具调用问题诊断                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """, BOLD + CYAN)

    results = {}

    # 1. 测试基本连接
    results['connection'] = await test_basic_connection()
    if not results['connection']:
        print_colored("\n⚠️ 基本连接失败，请检查服务是否运行", RED)
        return

    # 2. 测试简单对话
    results['simple_chat'] = await test_simple_chat()

    # 3. 测试工具调用
    results['tool_call'] = await test_tool_call_response()

    # 4. 直接测试 Z.AI（可选）
    results['direct_zai'] = await test_direct_zai_api()

    # 总结
    print_section("诊断总结")

    print_colored("测试结果:", BOLD)
    for test, result in results.items():
        if result is None:
            status = "⏭️  跳过"
            color = YELLOW
        elif result:
            status = "✅ 通过"
            color = GREEN
        else:
            status = "❌ 失败"
            color = RED
        print_colored(f"  {test:20} {status}", color)

    print()
    print_colored("🔍 问题定位:", BOLD + YELLOW)

    if not results['tool_call']:
        print_colored("""
可能的问题：
1. 工具调用参数格式不正确（缺少必需字段）
2. 工具名称与 Claude Code 期望的不匹配
3. 流式响应格式不符合 OpenAI 规范

建议：
1. 检查上面的工具调用参数分析
2. 确认工具名称是否正确
3. 验证参数中是否包含所有必需字段
        """, YELLOW)
    else:
        print_colored("工具调用测试通过，问题可能在 new-api 或 Claude Code 端", GREEN)

    print()
    print_colored("💡 下一步建议:", BOLD + CYAN)
    print("""
1. 如果参数缺少文件路径，考虑：
   - 设置 TOOL_SUPPORT=false 禁用工具调用
   - 或修改代码从上下文推断文件名

2. 如果工具名称不匹配，需要：
   - 在 z.ai2api_python 中添加工具名称映射

3. 如果格式都正确但仍然失败：
   - 问题可能在 new-api 的转换逻辑
   - 或 Claude Code 的工具执行逻辑
    """)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_colored("\n\n⚠️ 测试被中断", YELLOW)
    except Exception as e:
        print_colored(f"\n❌ 发生错误: {e}", RED)
        import traceback
        traceback.print_exc()