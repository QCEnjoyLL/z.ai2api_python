# z.ai2api_python 工具调用修复说明

## 问题描述

当通过 new-api 接入 z.ai2api_python 后在 Claude Code 中使用时，工具调用（如创建文件）会失败，错误信息为：
```
> 新建a.html
  ⎿  Error writing file
```

## 问题原因

z.ai2api_python 的 SSEToolHandler 在生成 OpenAI 格式的流式响应时存在以下不符合规范的问题：

1. **role 字段处理不当**：在每个块中都发送 role 字段，而规范要求只在第一个块中发送
2. **缺少必需字段**：缺少 `logprobs` 和 `system_fingerprint` 字段
3. **content 字段处理**：工具调用时未明确设置 `content: null`
4. **工具参数块格式**：重复发送了不必要的 `id` 字段
5. **完成块格式**：`finish_reason: "tool_calls"` 时，delta 应该是空对象而不是包含空数组

## 修复内容

### 1. 添加 role 发送状态跟踪

在 `SSEToolHandler.__init__` 中添加：
```python
self.has_sent_role = False  # 跟踪是否已发送 role 字段
```

### 2. 修改内容块创建逻辑

```python
def _create_content_chunk(self, content: str) -> Dict[str, Any]:
    chunk = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": self.model,
        "system_fingerprint": "fp_zai_001",
        "choices": [{
            "index": 0,
            "delta": {
                "content": content
            },
            "logprobs": None,
            "finish_reason": None
        }]
    }

    # 只有在第一次发送内容时才包含 role
    if not hasattr(self, 'has_sent_role') or not self.has_sent_role:
        chunk["choices"][0]["delta"]["role"] = "assistant"
        self.has_sent_role = True

    return chunk
```

### 3. 修改工具调用开始块

```python
def _create_tool_start_chunk(self) -> Dict[str, Any]:
    chunk = {
        # ... 基础结构 ...
        "system_fingerprint": "fp_zai_001",
        "choices": [{
            "index": 0,
            "delta": {
                "content": None,  # 明确设置 content 为 null
                "tool_calls": [{
                    # ... 工具调用信息 ...
                }]
            },
            "logprobs": None,
            "finish_reason": None
        }]
    }

    # 如果还没有发送过 role，在第一个工具调用块中添加
    if not hasattr(self, 'has_sent_role') or not self.has_sent_role:
        chunk["choices"][0]["delta"]["role"] = "assistant"
        self.has_sent_role = True

    return chunk
```

### 4. 修改工具参数块

```python
def _create_tool_arguments_chunk(self, arguments: str) -> Dict[str, Any]:
    return {
        # ... 基础结构 ...
        "choices": [{
            "index": 0,
            "delta": {
                "tool_calls": [{
                    "index": self.content_index,
                    # 不要重复发送 id，只发送参数更新
                    "function": {
                        "arguments": arguments
                    }
                }]
            },
            "logprobs": None,
            "finish_reason": None
        }]
    }
```

### 5. 修改完成块

```python
def _create_tool_finish_chunk(self) -> Dict[str, Any]:
    chunk = {
        # ... 基础结构 ...
        "choices": [{
            "index": 0,
            "delta": {},  # 完成时 delta 应该是空对象
            "logprobs": None,
            "finish_reason": "tool_calls"
        }]
    }
    # ...
```

## 测试方法

### 1. 重启 z.ai2api_python 服务

```bash
# 如果使用 Docker
docker restart z-ai2api-container-name

# 如果直接运行
# 停止服务后重新启动
python main.py
```

### 2. 在 Claude Code 中测试

1. 确保 new-api 已正确配置 z.ai2api_python 作为渠道
2. 在 Claude Code 中尝试创建文件：
   ```
   创建一个 test.html 文件，内容为简单的 HTML 页面
   ```

### 3. 验证日志

查看 z.ai2api_python 的日志，应该能看到：
- 工具调用被正确检测
- 参数被正确发送
- 没有格式错误

## 符合的 OpenAI API 规范

修复后的输出符合以下 OpenAI API 流式响应规范：

1. **首次消息**：包含 `role: "assistant"` 和 `content: null`（工具调用时）
2. **工具调用块**：
   - 第一个块：包含工具 id、name 和空 arguments
   - 后续块：只更新 arguments 内容
   - 完成块：delta 为空对象，finish_reason 为 "tool_calls"
3. **必需字段**：每个块都包含 `logprobs` 和 `system_fingerprint`
4. **状态管理**：正确跟踪和重置 role 发送状态

## 相关文件

- 修改文件：`app/utils/sse_tool_handler.py`
- 影响功能：工具调用（Function Call）的流式响应输出