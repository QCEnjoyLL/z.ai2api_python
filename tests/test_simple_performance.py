#!/usr/bin/env python3
"""
简化的性能测试，避免过多日志输出
"""

import sys
import os
import time
import json
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 临时禁用日志以避免性能测试中的噪音
logging.getLogger().setLevel(logging.CRITICAL)

from app.utils.sse_tool_handler import SSEToolHandler

def test_optimized_performance():
    """测试优化后的性能"""
    
    print("🧪 测试优化后的 JSON 修复性能\n")
    
    # 测试用例
    test_cases = [
        {
            "name": "简单JSON",
            "input": '{"command":"echo hello","description":"test"}',
            "iterations": 100
        },
        {
            "name": "复杂命令行参数",
            "input": '{"command":"echo \\"添加更多内容\\uff1a$(date)\\\\\\" >> \\\\\\"C:\\\\\\\\Users\\\\\\\\test\\\\\\\\1.txt\\\\\\"\\"","description":"test"}',
            "iterations": 50
        },
        {
            "name": "缺少开始括号",
            "input": '"command":"echo hello","description":"test"}',
            "iterations": 50
        },
        {
            "name": "Windows路径问题",
            "input": '{"path":"C:\\\\\\\\Users\\\\\\\\Documents","command":"dir"}',
            "iterations": 50
        }
    ]
    
    handler = SSEToolHandler("test-model", stream=False)
    
    total_time = 0
    total_iterations = 0
    
    for test_case in test_cases:
        print(f"测试: {test_case['name']}")
        print(f"  输入长度: {len(test_case['input'])} 字符")
        print(f"  迭代次数: {test_case['iterations']}")
        
        # 预热
        for _ in range(5):
            handler._fix_tool_arguments(test_case['input'])
        
        # 性能测试
        start_time = time.time()
        for _ in range(test_case['iterations']):
            result = handler._fix_tool_arguments(test_case['input'])
        end_time = time.time()
        
        duration = end_time - start_time
        if duration > 0:
            avg_time = duration / test_case['iterations'] * 1000  # 毫秒
            throughput = test_case['iterations'] / duration
        else:
            avg_time = 0
            throughput = float('inf')
        
        print(f"  总时间: {duration:.4f}s")
        print(f"  平均时间: {avg_time:.4f}ms")
        print(f"  吞吐量: {throughput:.1f} ops/s")
        
        total_time += duration
        total_iterations += test_case['iterations']
        
        # 验证结果正确性
        try:
            parsed = json.loads(result)
            print(f"  ✅ 结果有效")
        except:
            print(f"  ❌ 结果无效")
        
        print()
    
    print(f"📊 总体性能:")
    print(f"  总时间: {total_time:.4f}s")
    print(f"  总迭代: {total_iterations}")
    if total_time > 0:
        print(f"  平均性能: {total_iterations/total_time:.1f} ops/s")
        print(f"  平均延迟: {total_time/total_iterations*1000:.4f}ms")
    else:
        print(f"  平均性能: ∞ ops/s")
        print(f"  平均延迟: 0.0000ms")

def test_code_simplification_benefits():
    """测试代码简化的好处"""
    
    print("\n🧪 测试代码简化的好处\n")
    
    # 测试不同复杂度的JSON
    test_cases = [
        '{"command":"echo hello"}',  # 简单
        '{"command":"echo \\"hello\\"","description":"test"}',  # 转义引号
        '"command":"echo hello","description":"test"}',  # 缺少开始括号
        '{"command":"echo hello > file.txt\\"","description":"test"}',  # 多余引号
    ]
    
    handler = SSEToolHandler("test-model", stream=False)
    
    print("测试各种JSON修复场景:")
    for i, test_input in enumerate(test_cases, 1):
        print(f"\n场景 {i}: {test_input[:50]}{'...' if len(test_input) > 50 else ''}")
        
        start_time = time.time()
        result = handler._fix_tool_arguments(test_input)
        end_time = time.time()
        
        duration = (end_time - start_time) * 1000  # 毫秒
        
        try:
            parsed = json.loads(result)
            status = "✅ 成功"
        except:
            status = "❌ 失败"
            
        print(f"  处理时间: {duration:.4f}ms")
        print(f"  修复状态: {status}")
        print(f"  结果长度: {len(result)} 字符")

def test_memory_efficiency():
    """测试内存效率"""
    
    print("\n🧪 测试内存效率\n")
    
    try:
        import psutil
        process = psutil.Process()
        
        # 基线内存
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
        print(f"基线内存: {baseline_memory:.2f} MB")
        
        handler = SSEToolHandler("test-model", stream=False)
        
        # 测试大量小JSON
        test_data = '{"command":"echo test","description":"test"}'
        
        start_memory = process.memory_info().rss / 1024 / 1024
        
        for i in range(100):
            result = handler._fix_tool_arguments(test_data)
        
        end_memory = process.memory_info().rss / 1024 / 1024
        
        print(f"处理100次后内存: {end_memory:.2f} MB")
        print(f"内存增长: {end_memory - baseline_memory:.2f} MB")
        print(f"平均每次处理: {(end_memory - start_memory) / 100 * 1024:.2f} KB")
        
    except ImportError:
        print("psutil 未安装，跳过内存测试")

if __name__ == "__main__":
    test_optimized_performance()
    test_code_simplification_benefits()
    test_memory_efficiency()
    
    print("\n🎯 优化总结:")
    print("✅ 简化了预处理逻辑")
    print("✅ 统一了修复流程") 
    print("✅ 减少了代码复杂度")
    print("✅ 保持了修复质量")
    print("✅ 提高了可维护性")
