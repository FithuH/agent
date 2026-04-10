"""
core/parser.py
基于状态机的 LLM 响应解析器。
逐行解析 Markdown 格式的代码块，支持嵌套代码块和未闭合块的容错处理。
"""

import hashlib
from pathlib import Path
from typing import List, Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)


class FileArtifact:
    """从响应中提取的文件内容"""
    def __init__(self, path: str, content: str):
        self.path = Path(path)
        self.content = content


class ResponseParser:
    """基于状态机的 Markdown 代码块解析器"""

    def __init__(self):
        # 语言标识到文件扩展名的映射
        self.extension_map = {
            "python": ".py",
            "py": ".py",
            "javascript": ".js",
            "js": ".js",
            "typescript": ".ts",
            "ts": ".ts",
            "html": ".html",
            "css": ".css",
            "json": ".json",
            "yaml": ".yaml",
            "yml": ".yml",
            "markdown": ".md",
            "md": ".md",
            "bash": ".sh",
            "sh": ".sh",
            "shell": ".sh",
            "text": ".txt",
            "plaintext": ".txt",
        }
        # 收集非代码块的普通文本片段，用于最终 README 的合成
        self.text_fragments: List[str] = []

    def extract(self, response: str) -> List[FileArtifact]:
        """
        解析响应字符串，提取代码块并收集文本片段。

        Args:
            response: LLM 返回的原始字符串。

        Returns:
            提取到的所有文件产物列表。
        """
        artifacts: List[FileArtifact] = []
        lines = response.splitlines()

        # 状态变量
        in_block = False
        current_lang = ""
        current_content: List[str] = []
        nested_level = 0
        current_text_fragment: List[str] = []

        for raw_line in lines:
            line = raw_line.rstrip('\n\r')

            # 1. 检测代码块开始标记：以 ``` 开头且不在块内
            if line.startswith("```") and not in_block:
                # 结算之前积累的普通文本片段
                if current_text_fragment:
                    self.text_fragments.append("\n".join(current_text_fragment))
                    current_text_fragment.clear()

                # 进入代码块状态，提取语言标识
                lang_part = line[3:].strip()
                # 清洗语言标识：只保留字母数字和 +-# 等常见符号
                current_lang = self._sanitize_lang(lang_part)
                in_block = True
                nested_level = 0  # 初始嵌套深度为 0
                continue

            # 2. 处理代码块内部
            if in_block:
                # 遇到潜在的闭合标记（以 ``` 开头）
                if line.startswith("```"):
                    # 检查是否是纯闭合标记（只有空白符）
                    rest = line[3:].strip()
                    if rest == "":
                        # 纯 ```
                        if nested_level == 0:
                            # 外层代码块真正闭合
                            self._build_artifact(artifacts, current_content, current_lang)
                            # 重置状态
                            in_block = False
                            current_lang = ""
                            current_content = []
                        else:
                            # 嵌套块内部闭合，减少嵌套层级
                            nested_level -= 1
                            current_content.append(line)
                    else:
                        # 带有额外字符的 ```（例如 ```python 但已经在块内？这种情况可能是嵌套开始或误判）
                        # 通常嵌套块的开始标记会跟在内容后，我们将其视为嵌套开始，增加嵌套层级
                        nested_level += 1
                        current_content.append(line)
                else:
                    # 普通代码行，直接添加
                    current_content.append(line)
            else:
                # 3. 不在代码块内：收集普通文本行
                current_text_fragment.append(line)

        # 容错处理：循环结束后如果还在代码块内，说明响应被截断，强制抢救代码
        if in_block and current_content:
            logger.warning("检测到未闭合的代码块，将强制保存剩余内容。")
            self._build_artifact(artifacts, current_content, current_lang)

        # 处理残余的普通文本片段
        if current_text_fragment:
            self.text_fragments.append("\n".join(current_text_fragment))
            current_text_fragment.clear()

        # 如果一个代码块都没提取到，将整个响应作为一个文本文件保存
        if not artifacts:
            logger.warning("未找到任何代码块，将原始响应保存为 output.txt")
            artifacts.append(FileArtifact("output.txt", response))

        return artifacts

    def _sanitize_lang(self, lang: str) -> str:
        """
        清洗语言标识，去除可能的空白和特殊字符。
        只保留字母、数字、+、-、#。
        """
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+-#")
        return "".join(c for c in lang if c in allowed_chars)

    def _build_artifact(
        self,
        artifacts: List[FileArtifact],
        content_lines: List[str],
        lang: str
    ) -> None:
        """
        根据收集到的代码行和语言，构建 FileArtifact 并加入列表。
        会先移除可能存在的文件名注释行。
        """
        raw_code = "\n".join(content_lines)
        cleaned_code = self._clean_filename_comment(raw_code)

        filename = self._infer_filename(cleaned_code, lang)
        if filename is None:
            # 生成默认文件名：generated_哈希值.后缀
            hash_suffix = hashlib.md5(raw_code.encode()).hexdigest()[:6]
            ext = self.extension_map.get(lang, ".txt")
            filename = f"generated_{hash_suffix}{ext}"

        artifacts.append(FileArtifact(filename, cleaned_code))

    def _infer_filename(self, code: str, lang: str) -> Optional[str]:
        """
        从代码的前几行中推断文件名。
        查找包含 'filename:' 或 'file:' 的行，提取后面的文件名。
        不使用正则，仅用字符串操作。
        """
        lines = code.splitlines()
        # 只检查前5行，避免将注释中的 "filename" 误判
        for line in lines[:5]:
            line_lower = line.strip().lower()
            # 查找常见指示符
            indicator = None
            if "filename:" in line_lower:
                indicator = "filename:"
            elif "file:" in line_lower:
                indicator = "file:"
            else:
                continue

            # 提取指示符之后的内容
            idx = line_lower.find(indicator)
            if idx != -1:
                # 取原始行中对应部分之后的字符串
                after = line[idx + len(indicator):].strip()
                if after:
                    # 过滤掉非法文件名字符，只保留字母数字、点、下划线、横线、斜杠
                    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/\\")
                    filename = "".join(c for c in after if c in allowed)
                    if filename:
                        return filename

        # 兜底策略：根据语言给出默认文件名
        if lang.lower() in ("markdown", "md"):
            return "README.md"
        # 如果是常见编程语言，返回 main.后缀
        ext = self.extension_map.get(lang.lower(), ".txt")
        return f"main{ext}"

    def _clean_filename_comment(self, code: str) -> str:
        """
        如果代码第一行是文件名注释，则移除该行。
        注释形式包括： # filename: xxx, // file: xxx, /* file: xxx */
        """
        lines = code.splitlines()
        if not lines:
            return code

        first_line = lines[0].strip()
        first_lower = first_line.lower()

        # 检查是否包含指示符且以注释符开头
        is_filename_comment = False
        if (first_line.startswith("#") or first_line.startswith("//") or first_line.startswith("/*")) and \
           ("filename:" in first_lower or "file:" in first_lower):
            is_filename_comment = True

        if is_filename_comment:
            # 移除第一行，重新组合
            return "\n".join(lines[1:]).lstrip("\n")
        return code