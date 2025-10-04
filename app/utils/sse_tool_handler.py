#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SSE Tool Handler

处理 Z.AI SSE 流数据并转换为 OpenAI 兼容格式的工具调用处理器。

主要功能：
- 解析 glm_block 格式的工具调用
- 从 metadata.arguments 提取完整参数
- 支持多阶段处理：thinking → tool_call → other → answer
- 输出符合 OpenAI API 规范的流式响应
"""

import json
import time
from typing import Dict, Any, Generator
from enum import Enum

from app.utils.logger import get_logger

logger = get_logger()


class SSEPhase(Enum):
    """SSE 处理阶段枚举"""
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    OTHER = "other"
    ANSWER = "answer"
    DONE = "done"


class SSEToolHandler:
    """SSE 工具调用处理器"""

    def __init__(self, model: str, stream: bool = True, user_message: str = ""):
        self.model = model
        self.stream = stream
        self.user_message = user_message  # 保存用户消息，用于提取文件名

        # 状态管理
        self.current_phase = None
        self.has_tool_call = False
        self.has_sent_role = False  # 跟踪是否已发送 role 字段
        self.stream_ended = False  # 跟踪流是否已结束

        # 工具调用状态
        self.tool_id = ""
        self.tool_name = ""
        self.tool_args = ""
        self.tool_call_usage = {}
        self.content_index = 0  # 工具调用索引

        # 性能优化：内容缓冲
        self.content_buffer = ""
        self.buffer_size = 0
        self.last_flush_time = time.time()
        self.flush_interval = 0.05  # 50ms 刷新间隔
        self.max_buffer_size = 100  # 最大缓冲字符数

        logger.debug(f"🔧 初始化工具处理器: model={model}, stream={stream}")

    def process_sse_chunk(self, chunk_data: Dict[str, Any]) -> Generator[str, None, None]:
        """
        处理 SSE 数据块，返回 OpenAI 格式的流式响应

        Args:
            chunk_data: Z.AI SSE 数据块

        Yields:
            str: OpenAI 格式的 SSE 响应行
        """
        # 如果流已经结束，不再处理任何块
        if hasattr(self, 'stream_ended') and self.stream_ended:
            logger.info(f"🚫 流已结束，忽略后续块: phase={chunk_data.get('phase')}")
            return

        try:
            phase = chunk_data.get("phase")
            edit_content = chunk_data.get("edit_content", "")
            delta_content = chunk_data.get("delta_content", "")
            edit_index = chunk_data.get("edit_index")
            usage = chunk_data.get("usage", {})

            # 数据验证
            if not phase:
                logger.warning("⚠️ 收到无效的 SSE 块：缺少 phase 字段")
                return

            # 阶段变化检测和日志
            if phase != self.current_phase:
                # 阶段变化时强制刷新缓冲区
                if hasattr(self, 'content_buffer') and self.content_buffer:
                    yield from self._flush_content_buffer()

                logger.info(f"📈 SSE 阶段变化: {self.current_phase} → {phase}")
                content_preview = edit_content or delta_content
                if content_preview:
                    logger.debug(f"   📝 内容预览: {content_preview[:1000]}{'...' if len(content_preview) > 1000 else ''}")
                if edit_index is not None:
                    logger.debug(f"   📍 edit_index: {edit_index}")
                self.current_phase = phase

            # 根据阶段处理
            if phase == SSEPhase.THINKING.value:
                yield from self._process_thinking_phase(delta_content)

            elif phase == SSEPhase.TOOL_CALL.value:
                yield from self._process_tool_call_phase(edit_content)

            elif phase == SSEPhase.OTHER.value:
                yield from self._process_other_phase(usage, edit_content)

            elif phase == SSEPhase.ANSWER.value:
                yield from self._process_answer_phase(delta_content)

            elif phase == SSEPhase.DONE.value:
                yield from self._process_done_phase(chunk_data)
            else:
                logger.warning(f"⚠️ 未知的 SSE 阶段: {phase}")

        except Exception as e:
            logger.error(f"❌ 处理 SSE 块时发生错误: {e}")
            logger.debug(f"   📦 错误块数据: {chunk_data}")
            # 不中断流，继续处理后续块

    def _process_thinking_phase(self, delta_content: str) -> Generator[str, None, None]:
        """处理思考阶段"""
        if not delta_content:
            return

        logger.debug(f"🤔 思考内容: +{len(delta_content)} 字符")

        # 在流模式下输出思考内容
        if self.stream:
            chunk = self._create_content_chunk(delta_content)
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def _process_tool_call_phase(self, edit_content: str) -> Generator[str, None, None]:
        """处理工具调用阶段"""
        if not edit_content:
            return

        logger.debug(f"🔧 进入工具调用阶段，内容长度: {len(edit_content)}")

        # 检测 glm_block 标记
        if "<glm_block " in edit_content:
            yield from self._handle_glm_blocks(edit_content)
        else:
            # 没有 glm_block 标记，可能是参数补充
            if self.has_tool_call:
                # 只累积参数部分，找到第一个 ", "result"" 之前的内容
                result_pos = edit_content.find('", "result"')
                if result_pos > 0:
                    param_fragment = edit_content[:result_pos]
                    self.tool_args += param_fragment
                    logger.debug(f"📦 累积参数片段: {param_fragment}")
                else:
                    # 如果没有找到结束标记，累积整个内容（可能是中间片段）
                    self.tool_args += edit_content
                    logger.debug(f"📦 累积参数片段: {edit_content[:100]}...")

    def _handle_glm_blocks(self, edit_content: str) -> Generator[str, None, None]:
        """处理 glm_block 标记的内容"""
        blocks = edit_content.split('<glm_block ')
        logger.debug(f"📦 分割得到 {len(blocks)} 个块")

        for index, block in enumerate(blocks):
            if not block.strip():
                continue

            if index == 0:
                # 第一个块：提取参数片段
                if self.has_tool_call:
                    logger.debug(f"📦 从第一个块提取参数片段")
                    # 找到 "result" 的位置，提取之前的参数片段
                    result_pos = edit_content.find('"result"')
                    if result_pos > 0:
                        # 往前退3个字符去掉 ", "
                        param_fragment = edit_content[:result_pos - 3]
                        self.tool_args += param_fragment
                        logger.debug(f"📦 累积参数片段: {param_fragment}")
                else:
                    # 没有活跃工具调用，跳过第一个块
                    continue
            else:
                # 后续块：处理新工具调用
                if "</glm_block>" not in block:
                    continue

                # 如果有活跃的工具调用，先完成它
                if self.has_tool_call:
                    # 不要强行补全引号，让 json-repair 处理不完整的参数
                    logger.debug(f"🔧 完成前的参数: {self.tool_args[:200]}...")
                    yield from self._finish_current_tool()

                # 处理新工具调用
                yield from self._process_metadata_block(block)

    def _process_metadata_block(self, block: str) -> Generator[str, None, None]:
        """处理包含工具元数据的块"""
        try:
            # 提取 JSON 内容
            start_pos = block.find('>')
            end_pos = block.rfind('</glm_block>')

            if start_pos == -1 or end_pos == -1:
                logger.warning(f"❌ 无法找到 JSON 内容边界: {block[:1000]}...")
                return

            json_content = block[start_pos + 1:end_pos]
            logger.debug(f"📦 提取的 JSON 内容: {json_content[:1000]}...")

            # 解析工具元数据
            metadata_obj = json.loads(json_content)

            if "data" in metadata_obj and "metadata" in metadata_obj["data"]:
                metadata = metadata_obj["data"]["metadata"]

                # 调试：打印完整的元数据
                logger.info(f"📦 完整元数据: {json.dumps(metadata, ensure_ascii=False)[:500]}")

                # 开始新的工具调用
                self.tool_id = metadata.get("id", f"call_{int(time.time() * 1000000)}")
                self.tool_name = metadata.get("name", "unknown")
                self.has_tool_call = True

                logger.info(f"🎯 检测到工具调用: name={self.tool_name}, id={self.tool_id}")

                # 只有在这是第二个及以后的工具调用时才递增 index
                # 第一个工具调用应该使用 index 0

                # 从 metadata.arguments 获取参数起始部分
                if "arguments" in metadata:
                    arguments_str = metadata["arguments"]
                    # 直接使用原始参数，不要手动去掉最后的引号
                    # 因为参数可能是不完整的，json-repair 会处理
                    self.tool_args = arguments_str
                    logger.info(f"🎯 新工具调用: {self.tool_name}(id={self.tool_id}), 初始参数长度: {len(self.tool_args)}")
                    logger.debug(f"   参数预览: {self.tool_args[:200]}...")
                else:
                    self.tool_args = "{}"
                    logger.debug(f"🎯 新工具调用: {self.tool_name}(id={self.tool_id}), 空参数")

        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.error(f"❌ 解析工具元数据失败: {e}, 块内容: {block[:1000]}...")

        # 确保返回生成器（即使为空）
        if False:  # 永远不会执行，但确保函数是生成器
            yield

    def _process_other_phase(self, usage: Dict[str, Any], edit_content: str = "") -> Generator[str, None, None]:
        """处理其他阶段"""
        # 保存使用统计信息
        if usage:
            self.tool_call_usage = usage
            logger.debug(f"📊 保存使用统计: {usage}")

        # 工具调用完成判断：检测到 "null," 开头的 edit_content
        if self.has_tool_call and edit_content and edit_content.startswith("null,"):
            logger.info(f"🏁 检测到工具调用结束标记")

            # 完成当前工具调用
            yield from self._finish_current_tool()

            # 工具调用完成后，应该结束这个流
            # 因为 Claude Code 需要执行工具并发送结果后才会有新的对话
            yield "data: [DONE]\n\n"

            # 设置标记，阻止后续阶段的处理（必须在重置之前设置）
            self.stream_ended = True
            logger.info(f"🚫 设置 stream_ended = True，阻止后续处理")

            # 注意：不要重置所有状态，因为我们需要保持 stream_ended 标志
            # self._reset_all_state() 会重置 stream_ended，导致后续块仍然被处理

    def _process_answer_phase(self, delta_content: str) -> Generator[str, None, None]:
        """处理回答阶段（优化版本）"""
        if not delta_content:
            return

        logger.info(f"📝 工具处理器收到答案内容: {delta_content[:50]}...")

        # 工具调用完成后的答案内容处理
        # 注意：工具调用后的答案内容仍然是同一个助手消息的一部分，不需要新的 role
        if hasattr(self, 'tool_call_completed') and self.tool_call_completed:
            # 这是工具调用完成后的答案内容
            # 不需要发送新的 role，因为我们还在同一个流中
            logger.debug("📝 工具调用后的答案内容")
            # 清除标记，避免重复处理
            self.tool_call_completed = False

        # 添加到缓冲区
        self.content_buffer += delta_content
        self.buffer_size += len(delta_content)

        current_time = time.time()
        time_since_last_flush = current_time - self.last_flush_time

        # 检查是否需要刷新缓冲区
        should_flush = (
            self.buffer_size >= self.max_buffer_size or  # 缓冲区满了
            time_since_last_flush >= self.flush_interval or  # 时间间隔到了
            '\n' in delta_content or  # 包含换行符
            '。' in delta_content or '！' in delta_content or '？' in delta_content  # 包含句子结束符
        )

        if should_flush and self.content_buffer:
            yield from self._flush_content_buffer()

    def _flush_content_buffer(self) -> Generator[str, None, None]:
        """刷新内容缓冲区"""
        if not self.content_buffer:
            return

        logger.info(f"💬 工具处理器刷新缓冲区: {self.buffer_size} 字符 - {self.content_buffer[:50]}...")

        if self.stream:
            chunk = self._create_content_chunk(self.content_buffer)
            output_data = f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            logger.info(f"➡️ 工具处理器输出: {output_data[:100]}...")
            yield output_data

        # 清空缓冲区
        self.content_buffer = ""
        self.buffer_size = 0
        self.last_flush_time = time.time()

    def _process_done_phase(self, chunk_data: Dict[str, Any]) -> Generator[str, None, None]:
        """处理完成阶段"""
        logger.info("🏁 对话完成")

        # 先刷新任何剩余的缓冲内容
        if self.content_buffer:
            yield from self._flush_content_buffer()

        # 完成任何未完成的工具调用
        if self.has_tool_call:
            yield from self._finish_current_tool()

        # 发送流结束标记
        if self.stream:
            # 创建最终的完成块
            final_chunk = {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": self.model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }

            # 如果有 usage 信息，添加到最终块中
            if "usage" in chunk_data:
                final_chunk["usage"] = chunk_data["usage"]

            yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        # 重置所有状态
        self._reset_all_state()

    def _finish_current_tool(self) -> Generator[str, None, None]:
        """完成当前工具调用"""
        if not self.has_tool_call:
            return

        # 检查参数完整性 - 如果参数看起来不完整，不要强行补全
        # 因为强行补全可能会产生无效的 JSON
        raw_args = self.tool_args

        # 如果参数为空或只有开始括号，尝试使用空对象
        if not raw_args or raw_args in ['{', '{"']:
            logger.warning(f"⚠️ 工具参数为空或不完整: {repr(raw_args)}, 使用空对象")
            raw_args = "{}"

        # 修复参数格式
        fixed_args = self._fix_tool_arguments(raw_args)
        logger.debug(f"✅ 完成工具调用: {self.tool_name}, 参数: {fixed_args[:200]}")

        # 输出工具调用（开始 + 参数 + 完成）
        if self.stream:
            # 发送工具开始块
            start_chunk = self._create_tool_start_chunk()
            yield f"data: {json.dumps(start_chunk, ensure_ascii=False)}\n\n"

            # 发送参数块
            args_chunk = self._create_tool_arguments_chunk(fixed_args)
            yield f"data: {json.dumps(args_chunk, ensure_ascii=False)}\n\n"

            # 发送完成块
            finish_chunk = self._create_tool_finish_chunk()
            yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"

        # 重置工具状态
        self._reset_tool_state()

    def _fix_tool_arguments(self, raw_args: str) -> str:
        """使用 json-repair 库修复工具参数格式"""
        if not raw_args or raw_args == "{}":
            return "{}"

        logger.info(f"🔧 原始参数 ({len(raw_args)} 字符): {raw_args[:500]}{'...' if len(raw_args) > 500 else ''}")
        logger.debug(f"🔧 开始修复参数: {raw_args[:1000]}{'...' if len(raw_args) > 1000 else ''}")

        # 统一的修复流程：预处理 -> json-repair -> 后处理
        try:
            # 1. 预处理：只处理 json-repair 无法处理的问题
            processed_args = self._preprocess_json_string(raw_args.strip())

            # 2. 使用 json-repair 进行主要修复
            from json_repair import repair_json
            repaired_json = repair_json(processed_args)
            logger.debug(f"🔧 json-repair 修复结果: {repaired_json[:200]}")

            # 3. 解析JSON字符串为对象
            # json.loads 会自动解码 Unicode 转义序列（\uXXXX → 中文字符）
            args_obj = json.loads(repaired_json)
            logger.debug(f"🔧 JSON解析完成，对象类型: {type(args_obj)}, 键: {list(args_obj.keys())}")

            # 特殊处理：修复 Write 工具缺少 file_path 的问题
            if self.tool_name == "Write":
                logger.debug(f"🔍 Write工具参数检查: content存在={('content' in args_obj)}, file_path存在={('file_path' in args_obj)}")
                if "file_path" in args_obj:
                    logger.info(f"✅ Z.AI 已提供 file_path: {args_obj['file_path']}")

                if "content" in args_obj and "file_path" not in args_obj:
                    # 尝试从用户消息中提取文件名
                    file_path = self._extract_filename_from_context()
                    if file_path:
                        args_obj["file_path"] = file_path
                        logger.info(f"✅ 自动添加文件路径: {file_path}")
                    else:
                        # 如果无法提取，使用默认值
                        args_obj["file_path"] = "output.html"
                        logger.warning(f"⚠️ 无法从上下文提取文件名，使用默认值: output.html")

            # 其他文件操作工具的处理
            elif self.tool_name in ["write_file", "create_file", "str_replace_based_edit_tool", "str_replace_editor"]:
                if "content" in args_obj and "file_path" not in args_obj and "path" not in args_obj:
                    logger.warning(f"⚠️ 工具 {self.tool_name} 缺少文件路径参数")
                    file_path = self._extract_filename_from_context()
                    if file_path:
                        # 根据不同工具使用不同的字段名
                        path_field = "path" if self.tool_name == "str_replace_based_edit_tool" else "file_path"
                        args_obj[path_field] = file_path
                        logger.info(f"✅ 自动添加 {path_field}: {file_path}")

            # 4. 后处理：修复转义、路径等问题
            args_obj = self._post_process_args(args_obj)

            # 5. 序列化为 JSON 字符串
            # ensure_ascii=False 确保中文字符不被转义为 \uXXXX
            fixed_result = json.dumps(args_obj, ensure_ascii=False)
            logger.debug(f"🔧 最终JSON: {fixed_result[:200]}")

            return fixed_result

        except Exception as e:
            logger.error(f"❌ JSON 修复失败: {e}, 原始参数: {raw_args[:1000]}..., 使用空参数")
            return "{}"

    def _extract_filename_from_context(self) -> str:
        """从用户消息中提取文件名"""
        import re

        if not self.user_message:
            return ""

        # 清理用户消息中的系统标记
        cleaned_message = self.user_message
        # 移除 Claude Code 的中断标记和其他系统标记
        system_markers = [
            '[Request interrupted by user]',
            '[CANCELLED]',
            '[STOPPED]',
        ]
        for marker in system_markers:
            if marker in cleaned_message:
                cleaned_message = cleaned_message.replace(marker, '').strip()
                logger.debug(f"🧹 清理系统标记: {marker}")

        # 常见的文件名模式
        patterns = [
            r'(?:创建|新建|生成|写入|保存为?|文件名?[为是：:]\s*)([a-zA-Z0-9_\-]+\.(?:html|js|css|txt|md|json|xml|py|java|cpp|c|h|go|rs|php|rb|sh|bat|sql|yaml|yml))',
            r'([a-zA-Z0-9_\-]+\.(?:html|js|css|txt|md|json|xml|py|java|cpp|c|h|go|rs|php|rb|sh|bat|sql|yaml|yml))(?:\s*文件)?',
            r'(?:名为|叫做?|称为)\s*([a-zA-Z0-9_\-]+\.(?:html|js|css|txt|md|json|xml|py|java|cpp|c|h|go|rs|php|rb|sh|bat|sql|yaml|yml))',
        ]

        for pattern in patterns:
            match = re.search(pattern, cleaned_message, re.IGNORECASE)
            if match:
                filename = match.group(1)
                logger.info(f"📁 从用户消息中提取到文件名: {filename}")
                return filename

        # 如果没有明确的文件扩展名，尝试更宽松的匹配
        # 例如 "a.html" 或 "test.js"
        simple_pattern = r'\b([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)\b'
        matches = re.findall(simple_pattern, cleaned_message)
        if matches:
            # 返回第一个看起来像文件名的匹配
            for match in matches:
                # 检查扩展名是否合理
                if '.' in match:
                    ext = match.split('.')[-1].lower()
                    if len(ext) <= 4:  # 扩展名通常不超过4个字符
                        logger.info(f"📁 找到可能的文件名: {match}")
                        return match

        # 根据内容关键词推断文件名
        keyword_mapping = {
            r'登录页面|登陆页面|login.*页面': 'login.html',
            r'注册页面|signup.*页面|register.*页面': 'register.html',
            r'主页|首页|index.*页面|home.*页面': 'index.html',
            r'关于页面|about.*页面': 'about.html',
            r'联系页面|contact.*页面': 'contact.html',
        }

        for pattern, filename in keyword_mapping.items():
            if re.search(pattern, cleaned_message, re.IGNORECASE):
                logger.info(f"📁 根据关键词推断文件名: {filename}")
                return filename

        logger.debug(f"❌ 无法从消息中提取文件名: {self.user_message[:100]}...")
        return ""

    def _post_process_args(self, args_obj: Dict[str, Any]) -> Dict[str, Any]:
        """统一的后处理方法"""
        # 修复双重Unicode转义（如 \\u7528 -> 用）
        args_obj = self._fix_unicode_escaping(args_obj)

        # 注意：不再调用 _fix_string_escaping()
        # 因为 json.loads() 已经正确解析了所有转义序列
        # 额外的转义修复会破坏已经正确的数据结构

        # 修复路径中的过度转义（仅针对特定路径问题）
        args_obj = self._fix_path_escaping_in_args(args_obj)

        # 修复命令中的多余引号
        args_obj = self._fix_command_quotes(args_obj)

        return args_obj

    def _fix_unicode_escaping(self, args_obj: Dict[str, Any]) -> Dict[str, Any]:
        """修复双重Unicode转义问题"""
        import re
        import codecs

        def decode_unicode_escapes(text: str) -> str:
            """安全地解码Unicode转义序列"""
            if '\\u' not in text:
                return text

            try:
                # 使用正则表达式替换 \uXXXX 序列
                def replace_unicode(match):
                    code = match.group(1)
                    return chr(int(code, 16))

                # 匹配 \uXXXX 格式（4位十六进制）
                decoded = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, text)

                if decoded != text:
                    logger.debug(f"🔧 Unicode解码: {len(text)} -> {len(decoded)} 字符")

                return decoded
            except Exception as e:
                logger.debug(f"⚠️ Unicode解码失败: {e}, 保持原值")
                return text

        for key, value in args_obj.items():
            if isinstance(value, str):
                args_obj[key] = decode_unicode_escapes(value)

            elif isinstance(value, dict):
                args_obj[key] = self._fix_unicode_escaping(value)

            elif isinstance(value, list):
                fixed_list = []
                for item in value:
                    if isinstance(item, dict):
                        fixed_list.append(self._fix_unicode_escaping(item))
                    elif isinstance(item, str):
                        fixed_list.append(decode_unicode_escapes(item))
                    else:
                        fixed_list.append(item)
                args_obj[key] = fixed_list

        return args_obj

    def _fix_string_escaping(self, args_obj: Dict[str, Any]) -> Dict[str, Any]:
        """递归修复所有字符串值中的过度转义"""
        for key, value in args_obj.items():
            if isinstance(value, str):
                original = value
                modified = False

                # 修复 \" -> "
                if '\\"' in value:
                    value = value.replace('\\"', '"')
                    modified = True

                # 修复 \\n -> \n (换行符)
                if '\\n' in value:
                    value = value.replace('\\n', '\n')
                    modified = True

                # 修复其他常见的转义序列
                if '\\t' in value:
                    value = value.replace('\\t', '\t')
                    modified = True

                if modified:
                    args_obj[key] = value
                    logger.debug(f"🔧 修复字段 {key} 的转义: {len(original)} -> {len(value)} 字符")

            elif isinstance(value, dict):
                # 递归处理嵌套字典
                args_obj[key] = self._fix_string_escaping(value)

            elif isinstance(value, list):
                # 递归处理列表中的每个元素
                fixed_list = []
                for item in value:
                    if isinstance(item, dict):
                        fixed_list.append(self._fix_string_escaping(item))
                    elif isinstance(item, str):
                        # 修复列表中的字符串
                        fixed_item = item
                        if '\\"' in item:
                            fixed_item = item.replace('\\"', '"')
                        if '\\n' in fixed_item:
                            fixed_item = fixed_item.replace('\\n', '\n')
                        if '\\t' in fixed_item:
                            fixed_item = fixed_item.replace('\\t', '\t')
                        fixed_list.append(fixed_item)
                    else:
                        fixed_list.append(item)
                args_obj[key] = fixed_list

        return args_obj

    def _preprocess_json_string(self, text: str) -> str:
        """预处理 JSON 字符串，只处理 json-repair 无法处理的问题"""
        import re

        # 只保留 json-repair 无法处理的预处理步骤

        # 1. 修复缺少开始括号的情况（json-repair 无法处理）
        if not text.startswith('{') and text.endswith('}'):
            text = '{' + text
            logger.debug(f"🔧 补全开始括号")

        # 2. 修复末尾多余的反斜杠和引号（json-repair 可能处理不当）
        # 匹配模式：字符串值末尾的 \" 后面跟着 } 或 ,
        # 例如：{"url":"https://www.bilibili.com\"} -> {"url":"https://www.bilibili.com"}
        # 例如：{"url":"https://www.bilibili.com\",} -> {"url":"https://www.bilibili.com",}
        pattern = r'([^\\])\\"([}\s,])'
        if re.search(pattern, text):
            text = re.sub(pattern, r'\1"\2', text)
            logger.debug(f"🔧 修复末尾多余的反斜杠")

        return text

    def _fix_path_escaping_in_args(self, args_obj: Dict[str, Any]) -> Dict[str, Any]:
        """修复参数对象中路径的过度转义问题"""
        import re

        # 需要检查的路径字段
        path_fields = ['file_path', 'path', 'directory', 'folder']

        for field in path_fields:
            if field in args_obj and isinstance(args_obj[field], str):
                path_value = args_obj[field]

                # 检查是否是Windows路径且包含过度转义
                if path_value.startswith('C:') and '\\\\' in path_value:
                    logger.debug(f"🔍 检查路径字段 {field}: {repr(path_value)}")

                    # 分析路径结构：正常路径应该是 C:\Users\...
                    # 但过度转义的路径可能是 C:\Users\\Documents（多了一个反斜杠）
                    # 我们需要找到不正常的双反斜杠模式并修复

                    # 先检查是否有不正常的双反斜杠（不在路径开头）
                    # 正常：C:\Users\Documents
                    # 异常：C:\Users\\Documents 或 C:\Users\\\\Documents

                    # 使用更精确的模式：匹配路径分隔符后的额外反斜杠
                    # 但要保留正常的路径分隔符
                    fixed_path = path_value

                    # 检查是否有连续的多个反斜杠（超过正常的路径分隔符）
                    if '\\\\' in path_value:
                        # 计算反斜杠的数量，如果超过正常数量就修复
                        parts = path_value.split('\\')
                        # 重新组装路径，去除空的部分（由多余的反斜杠造成）
                        clean_parts = [part for part in parts if part]
                        if len(clean_parts) > 1:
                            fixed_path = '\\'.join(clean_parts)

                    logger.debug(f"🔍 修复后路径: {repr(fixed_path)}")

                    if fixed_path != path_value:
                        args_obj[field] = fixed_path
                        logger.debug(f"🔧 修复字段 {field} 的路径转义: {path_value} -> {fixed_path}")
                    else:
                        logger.debug(f"🔍 路径无需修复: {path_value}")

        return args_obj

    def _fix_command_quotes(self, args_obj: Dict[str, Any]) -> Dict[str, Any]:
        """修复命令中的多余引号问题"""
        import re

        # 检查命令字段
        if 'command' in args_obj and isinstance(args_obj['command'], str):
            command = args_obj['command']

            # 检查是否以双引号结尾（多余的引号）
            if command.endswith('""'):
                logger.debug(f"🔧 发现命令末尾多余引号: {command}")
                # 移除最后一个多余的引号
                fixed_command = command[:-1]
                args_obj['command'] = fixed_command
                logger.debug(f"🔧 修复命令引号: {command} -> {fixed_command}")

            # 检查其他可能的引号问题
            # 例如：路径末尾的 \"" 模式
            elif re.search(r'\\""+$', command):
                logger.debug(f"🔧 发现命令末尾引号模式问题: {command}")
                # 修复路径末尾的引号问题
                fixed_command = re.sub(r'\\""+$', '\\"', command)
                args_obj['command'] = fixed_command
                logger.debug(f"🔧 修复命令引号模式: {command} -> {fixed_command}")

        return args_obj

    def _create_content_chunk(self, content: str) -> Dict[str, Any]:
        """创建内容块"""
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

    def _create_tool_start_chunk(self) -> Dict[str, Any]:
        """创建工具开始块"""
        chunk = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "system_fingerprint": "fp_zai_001",
            "choices": [{
                "index": 0,
                "delta": {
                    "content": None,  # 明确设置 content 为 null
                    "tool_calls": [{
                        "index": self.content_index,
                        "id": self.tool_id,
                        "type": "function",
                        "function": {
                            "name": self.tool_name,
                            "arguments": ""
                        }
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

    def _create_tool_arguments_chunk(self, arguments: str) -> Dict[str, Any]:
        """创建工具参数块"""
        # 安全的参数预览（避免泄露敏感路径）
        try:
            args_preview = json.loads(arguments) if arguments else {}
            # 移除可能包含路径的字段
            safe_preview = {k: (v if k not in ['file_path', 'path', 'directory'] else '[REDACTED]')
                           for k, v in (args_preview.items() if isinstance(args_preview, dict) else [])}
            logger.info(f"📤 发送参数: {json.dumps(safe_preview, ensure_ascii=False)[:200]}")
        except:
            logger.info(f"📤 发送参数: {arguments[:50]}...")

        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "system_fingerprint": "fp_zai_001",
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

    def _create_tool_finish_chunk(self) -> Dict[str, Any]:
        """创建工具完成块"""
        chunk = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "system_fingerprint": "fp_zai_001",
            "choices": [{
                "index": 0,
                "delta": {},  # 完成时 delta 应该是空对象
                "logprobs": None,
                "finish_reason": "tool_calls"
            }]
        }

        # 添加使用统计（如果有）
        if self.tool_call_usage:
            chunk["usage"] = self.tool_call_usage

        return chunk

    def _reset_tool_state(self):
        """重置工具状态"""
        self.tool_id = ""
        self.tool_name = ""
        self.tool_args = ""
        self.has_tool_call = False
        # content_index 在单次对话中应该保持不变，只有在新的工具调用开始时才递增

    def _reset_all_state(self):
        """重置所有状态"""
        # 先刷新任何剩余的缓冲内容
        if hasattr(self, 'content_buffer') and self.content_buffer:
            list(self._flush_content_buffer())  # 消费生成器

        self._reset_tool_state()
        self.current_phase = None
        self.tool_call_usage = {}
        self.has_sent_role = False  # 重置 role 发送标志
        self.stream_ended = False  # 重置流结束标志

        # 重置缓冲区
        self.content_buffer = ""
        self.buffer_size = 0
        self.last_flush_time = time.time()

        # content_index 重置为 0，为下一轮对话做准备
        self.content_index = 0
        logger.debug("🔄 重置所有处理器状态")
