#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试 LongCat API 连接性
"""

import asyncio
import httpx
import json

# LongCat API 端点
LONGCAT_API_ENDPOINT = "https://longcat.chat/api/v1/chat-completion-oversea"

async def test_longcat_api():
    """测试 LongCat API 连接"""
    print(f"🧪 测试 LongCat API 连接...")
    print(f"📡 API 端点: {LONGCAT_API_ENDPOINT}")
    
    headers = {
        'accept': 'text/event-stream,application/json',
        'content-type': 'application/json',
        'origin': 'https://longcat.chat',
        'referer': 'https://longcat.chat/t',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
    }
    
    payload = {
        "stream": True,
        "temperature": 0.7,
        "content": "Hello",
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            }
        ]
    }
    
    print(f"📤 发送请求...")
    print(f"📋 Headers: {json.dumps(headers, indent=2)}")
    print(f"📋 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                LONGCAT_API_ENDPOINT,
                headers=headers,
                json=payload
            )
            
            print(f"📡 响应状态码: {response.status_code}")
            print(f"📋 响应头: {dict(response.headers)}")
            
            if not response.is_success:
                error_text = await response.atext()
                print(f"❌ API 错误: {error_text}")
                return False
            
            print(f"✅ 连接成功，开始读取流数据...")
            
            line_count = 0
            async for line in response.aiter_lines():
                line_count += 1
                line = line.strip()
                print(f"📥 第 {line_count} 行: {line}")
                
                if line_count > 10:  # 只读取前10行
                    print(f"⏹️ 停止读取（已读取 {line_count} 行）")
                    break
                    
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str == '[DONE]':
                        print(f"🏁 收到结束标记")
                        break
                    
                    try:
                        data = json.loads(data_str)
                        print(f"📦 解析成功: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON 解析失败: {e}")
            
            print(f"✅ 测试完成，共读取 {line_count} 行")
            return True
            
    except httpx.TimeoutException:
        print(f"❌ 请求超时")
        return False
    except httpx.ConnectError as e:
        print(f"❌ 连接错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        import traceback
        print(f"❌ 错误堆栈: {traceback.format_exc()}")
        return False

async def test_simple_request():
    """测试简单的非流式请求"""
    print(f"\n🧪 测试简单的非流式请求...")
    
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'origin': 'https://longcat.chat',
        'referer': 'https://longcat.chat/t',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    payload = {
        "stream": False,
        "temperature": 0.7,
        "content": "Hello",
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            }
        ]
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                LONGCAT_API_ENDPOINT,
                headers=headers,
                json=payload
            )
            
            print(f"📡 响应状态码: {response.status_code}")
            
            if response.is_success:
                content = await response.atext()
                print(f"✅ 响应内容: {content[:500]}...")
                return True
            else:
                error_text = await response.atext()
                print(f"❌ 错误响应: {error_text}")
                return False
                
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

async def main():
    """运行所有测试"""
    print("🚀 开始 LongCat API 连接测试...\n")
    
    # 测试流式请求
    stream_result = await test_longcat_api()
    
    # 测试非流式请求
    simple_result = await test_simple_request()
    
    print(f"\n📊 测试结果:")
    print(f"  流式请求: {'✅ 成功' if stream_result else '❌ 失败'}")
    print(f"  非流式请求: {'✅ 成功' if simple_result else '❌ 失败'}")
    
    if stream_result and simple_result:
        print(f"🎉 所有测试通过！")
    else:
        print(f"⚠️ 部分测试失败，请检查网络连接和 API 端点")

if __name__ == "__main__":
    asyncio.run(main())
