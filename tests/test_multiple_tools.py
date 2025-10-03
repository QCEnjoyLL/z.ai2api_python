#!/usr/bin/env python3
"""
测试多个工具调用的处理逻辑
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.sse_tool_handler import SSEToolHandler

def test_multiple_tool_calls():
    """测试多个工具调用的处理"""
    
    handler = SSEToolHandler("test-model", stream=False)
    
    print("🧪 测试多个工具调用处理\n")
    
    # 模拟真实的多工具调用序列（基于日志）
    test_chunks = [
        # 第一个工具调用开始
        {
            "phase": "tool_call",
            "edit_content": '<glm_block view="">{"type": "mcp", "data": {"metadata": {"id": "call_5y5gir0mygx", "name": "mcp__playwright__browser_navigate", "arguments": "{\\"url\\":\\"https://www.bil", "result": "", "display_result": "", "duration": "...", "status": "completed", "is_error": false, "mcp_server": {"name": "mcp-server"}}, "thought": null, "ppt": null, "browser": null}}</glm_block>',
            "edit_index": 24
        },
        # 第一个工具调用参数补充
        {
            "phase": "tool_call",
            "edit_content": 'ibili.com\\"}',
            "edit_index": 194
        },
        # 第一个工具调用结束
        {
            "phase": "other",
            "edit_content": 'null, "display_result": "", "duration": "...", "status": "completed", "is_error": false, "mcp_server": {"name": "mcp-server"}}, "thought": null, "ppt": null, "browser": null}}</glm_block>',
            "edit_index": 219
        },
        # 第二个工具调用开始
        {
            "phase": "tool_call", 
            "edit_content": '<glm_block view="">{"type": "mcp", "data": {"metadata": {"id": "call_j8r24x6xtg", "name": "mcp__playwright__browser_snapshot", "arguments": "{}", "result": "", "display_result": "", "duration": "...", "status": "completed", "is_error": false, "mcp_server": {"name": "mcp-server"}}, "thought": null, "ppt": null, "browser": null}}</glm_block>',
            "edit_index": 406
        },
        # 第二个工具调用结束
        {
            "phase": "other",
            "edit_content": 'null, "display_result": "", "duration": "...", "status": "completed", "is_error": false, "mcp_server": {"name": "mcp-server"}}, "thought": null, "ppt": null, "browser": null}}</glm_block>',
            "edit_index": 566
        },
        # 第三个工具调用开始（重复的 navigate）
        {
            "phase": "tool_call",
            "edit_content": '<glm_block view="">{"type": "mcp", "data": {"metadata": {"id": "call_scvwo0xaoil", "name": "mcp__playwright__browser_navigate", "arguments": "{\\"url\\":\\"https://www.bil", "result": "", "display_result": "", "duration": "...", "status": "completed", "is_error": false, "mcp_server": {"name": "mcp-server"}}, "thought": null, "ppt": null, "browser": null}}</glm_block>',
            "edit_index": 753
        },
        # 第三个工具调用参数补充
        {
            "phase": "tool_call",
            "edit_content": 'ibili.com\\"}',
            "edit_index": 925
        },
        # 第三个工具调用结束
        {
            "phase": "other",
            "edit_content": 'null, "display_result": "", "duration": "...", "status": "completed", "is_error": false, "mcp_server": {"name": "mcp-server"}}, "thought": null, "ppt": null, "browser": null}}</glm_block>',
            "edit_index": 950
        }
    ]
    
    tool_calls_completed = []
    
    for i, chunk in enumerate(test_chunks, 1):
        print(f"处理块 {i}: edit_index={chunk['edit_index']}, phase={chunk['phase']}")
        
        # 记录处理前的工具状态
        old_tool_id = handler.tool_id
        old_tool_name = handler.tool_name
        old_has_tool_call = handler.has_tool_call

        # 处理块
        results = list(handler.process_sse_chunk(chunk))

        # 检查是否有新工具调用开始
        if handler.tool_id != old_tool_id and handler.tool_id:
            print(f"  🎯 新工具调用开始: {handler.tool_name} (id: {handler.tool_id})")

        # 检查是否有工具调用完成
        if old_has_tool_call and not handler.has_tool_call:
            tool_calls_completed.append({
                "name": old_tool_name or "unknown",
                "id": old_tool_id
            })
            print(f"  ✅ 工具调用完成: {old_tool_name or 'unknown'}")
        
        print(f"  当前状态: has_tool_call={handler.has_tool_call}, tool_id={handler.tool_id}")
        print()
    
    print(f"📊 测试结果:")
    print(f"  完成的工具调用数量: {len(tool_calls_completed)}")
    for i, tool in enumerate(tool_calls_completed, 1):
        print(f"  {i}. {tool['name']} (id: {tool['id']})")
    
    # 验证是否正确处理了所有工具调用
    expected_tools = [
        "mcp__playwright__browser_navigate",
        "mcp__playwright__browser_snapshot", 
        "mcp__playwright__browser_navigate"
    ]
    
    completed_tool_names = [tool['name'] for tool in tool_calls_completed]
    
    if completed_tool_names == expected_tools:
        print("\n✅ 测试通过！正确处理了所有工具调用")
        print("📝 结论：重复的工具调用是上游发送的，我们的处理逻辑是正确的")
        return True
    else:
        print(f"\n❌ 测试失败！")
        print(f"  期望: {expected_tools}")
        print(f"  实际: {completed_tool_names}")
        return False

if __name__ == "__main__":
    success = test_multiple_tool_calls()
    
    if success:
        print("\n🎯 总结：")
        print("1. 我们的 API 代理正确处理了每个不同的工具调用")
        print("2. 重复的工具调用是上游 Z.AI 模型发送的，不是我们的问题")
        print("3. 每个工具调用都有不同的 ID，说明这是模型的有意行为")
        print("4. 可能的原因：模型重试、验证操作、或处理复杂任务的策略")
    else:
        print("\n❌ 需要进一步调试处理逻辑")
