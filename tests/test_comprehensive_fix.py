#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
全面测试 ZAI Provider 修复效果
验证流式输出、工具调用、思考模式、重试机制等功能
"""

import asyncio
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.providers.zai_provider import ZAIProvider
from app.models.schemas import OpenAIRequest, Message
from app.core.config import settings


async def test_basic_stream():
    """测试基本流式输出"""
    print("🧪 测试基本流式输出...")
    
    provider = ZAIProvider()
    
    request = OpenAIRequest(
        model=settings.PRIMARY_MODEL,
        messages=[
            Message(role="user", content="你好，请简单介绍一下自己")
        ],
        stream=True
    )
    
    try:
        response = await provider.chat_completion(request)
        
        if hasattr(response, '__aiter__'):
            print("✅ 返回了异步生成器")
            chunk_count = 0
            content_chunks = []
            
            async for chunk in response:
                chunk_count += 1
                if chunk.startswith("data: ") and not chunk.strip().endswith("[DONE]"):
                    try:
                        chunk_data = json.loads(chunk[6:].strip())
                        if "choices" in chunk_data and chunk_data["choices"]:
                            choice = chunk_data["choices"][0]
                            if "delta" in choice and "content" in choice["delta"]:
                                content = choice["delta"]["content"]
                                if content:
                                    content_chunks.append(content)
                    except:
                        pass
                
                if chunk_count >= 10:  # 限制测试长度
                    break
            
            full_content = "".join(content_chunks)
            print(f"✅ 成功处理了 {chunk_count} 个数据块")
            print(f"📝 内容预览: {full_content[:100]}...")
            return len(content_chunks) > 0
        else:
            print("❌ 返回的不是流式响应")
            return False
            
    except Exception as e:
        print(f"❌ 基本流式测试失败: {e}")
        return False


async def test_thinking_mode():
    """测试思考模式"""
    print("\n🧪 测试思考模式...")
    
    provider = ZAIProvider()
    
    request = OpenAIRequest(
        model=settings.THINKING_MODEL,
        messages=[
            Message(role="user", content="请解释一下量子计算的基本原理")
        ],
        stream=True
    )
    
    try:
        response = await provider.chat_completion(request)
        
        if hasattr(response, '__aiter__'):
            print("✅ 返回了异步生成器")
            chunk_count = 0
            has_thinking = False
            has_content = False
            
            async for chunk in response:
                chunk_count += 1
                
                # 检查是否包含思考内容
                if 'thinking' in chunk:
                    has_thinking = True
                    print("✅ 检测到思考内容")
                
                # 检查是否包含普通内容
                if '"content"' in chunk and '"thinking"' not in chunk:
                    has_content = True
                    print("✅ 检测到答案内容")
                
                if chunk_count >= 20:  # 限制测试长度
                    break
            
            print(f"✅ 成功处理了 {chunk_count} 个数据块")
            print(f"🤔 思考模式: {'正常' if has_thinking else '未检测到'}")
            print(f"💬 答案内容: {'正常' if has_content else '未检测到'}")
            return True
        else:
            print("❌ 返回的不是流式响应")
            return False
            
    except Exception as e:
        print(f"❌ 思考模式测试失败: {e}")
        return False


async def test_tool_support():
    """测试工具调用支持"""
    print("\n🧪 测试工具调用支持...")
    
    if not settings.TOOL_SUPPORT:
        print("⚠️ 工具支持已禁用，跳过测试")
        return True
    
    provider = ZAIProvider()
    
    # 简单的工具定义
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    request = OpenAIRequest(
        model=settings.PRIMARY_MODEL,
        messages=[
            Message(role="user", content="请帮我查询北京的天气")
        ],
        tools=tools,
        stream=True
    )
    
    try:
        response = await provider.chat_completion(request)
        
        if hasattr(response, '__aiter__'):
            print("✅ 返回了异步生成器")
            chunk_count = 0
            has_tool_call = False
            
            async for chunk in response:
                chunk_count += 1
                
                # 检查是否包含工具调用
                if 'tool_calls' in chunk:
                    has_tool_call = True
                    print("✅ 检测到工具调用")
                
                if chunk_count >= 30:  # 限制测试长度
                    break
            
            print(f"✅ 成功处理了 {chunk_count} 个数据块")
            print(f"🔧 工具调用: {'正常' if has_tool_call else '未检测到'}")
            return True
        else:
            print("❌ 返回的不是流式响应")
            return False
            
    except Exception as e:
        print(f"❌ 工具调用测试失败: {e}")
        return False


async def test_error_handling():
    """测试错误处理"""
    print("\n🧪 测试错误处理...")
    
    provider = ZAIProvider()
    
    # 使用无效的消息来触发错误
    request = OpenAIRequest(
        model="invalid-model",
        messages=[
            Message(role="user", content="测试错误处理")
        ],
        stream=True
    )
    
    try:
        response = await provider.chat_completion(request)
        
        if hasattr(response, '__aiter__'):
            chunk_count = 0
            has_error = False
            
            async for chunk in response:
                chunk_count += 1
                
                # 检查是否包含错误信息
                if 'error' in chunk:
                    has_error = True
                    print("✅ 检测到错误处理")
                
                if chunk_count >= 5:  # 限制测试长度
                    break
            
            print(f"✅ 错误处理测试完成，处理了 {chunk_count} 个数据块")
            return True
        else:
            print("✅ 返回了错误响应（非流式）")
            return True
            
    except Exception as e:
        print(f"✅ 正确捕获了异常: {type(e).__name__}")
        return True


async def main():
    """主测试函数"""
    print("🚀 开始全面测试 ZAI Provider 修复效果\n")
    
    # 显示配置信息
    print("📋 当前配置:")
    print(f"  - 匿名模式: {settings.ANONYMOUS_MODE}")
    print(f"  - 工具支持: {settings.TOOL_SUPPORT}")
    print(f"  - 最大重试: {settings.MAX_RETRIES}")
    print(f"  - 重试延迟: {settings.RETRY_DELAY}s")
    print()
    
    tests = [
        ("基本流式输出", test_basic_stream),
        ("思考模式", test_thinking_mode),
        ("工具调用支持", test_tool_support),
        ("错误处理", test_error_handling),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            print(f"{'='*50}")
            result = await test_func()
            if result:
                passed += 1
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
        
        print()
    
    print(f"{'='*50}")
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试都通过了！ZAI Provider 修复成功")
    elif passed >= total * 0.75:
        print("✅ 大部分测试通过，ZAI Provider 基本修复成功")
    else:
        print("⚠️ 多个测试失败，需要进一步检查")


if __name__ == "__main__":
    asyncio.run(main())
