"""
core/parser.py
双模解析器：生成时强制指定文件名防幻觉；调试时通过注释自动判定要覆盖的文件。
"""
import re
from pathlib import Path
from typing import List, Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

class FileArtifact:
    def __init__(self, path: str, content: str):
        self.path = Path(path)
        self.content = content

class ResponseParser:
    def __init__(self):
        pass

    def extract(self, response: str, expected_filename: Optional[str] = None) -> List[FileArtifact]:
        blocks = self._extract_markdown_blocks(response)
        
        if not blocks:
            # 如果 AI 没有输出 Markdown 块，把整体作为代码
            blocks = [response.strip()]

        artifacts = []
        
        if expected_filename:
            # 【生成模式：独裁命名】无视内部注释，强制锁定文件名
            raw_code = max(blocks, key=len)
            cleaned_code = self._clean_filename_comment(raw_code)
            artifacts.append(FileArtifact(expected_filename, cleaned_code))
        else:
            # 【调试模式：自治识别】允许多个文件输出，依靠注释精准替换
            for block in blocks:
                fname = self._infer_filename(block)
                if fname:
                    cleaned_code = self._clean_filename_comment(block)
                    artifacts.append(FileArtifact(fname, cleaned_code))
                    logger.info(f"提取到修复代码文件: {fname}")
                    
        return artifacts

    def _extract_markdown_blocks(self, text: str) -> List[str]:
        blocks = []
        in_block = False
        current = []
        for line in text.splitlines():
            if line.strip().startswith("```"):
                if not in_block:
                    in_block = True
                else:
                    in_block = False
                    blocks.append("\n".join(current).strip())
                    current = []
            elif in_block:
                current.append(line)
        if in_block and current:
            blocks.append("\n".join(current).strip())
        return blocks

    def _infer_filename(self, code: str) -> Optional[str]:
        for line in code.splitlines()[:5]:
            match = re.search(r'(?:filename|file):\s*([a-zA-Z0-9_.-]+)', line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _clean_filename_comment(self, code: str) -> str:
        lines = code.splitlines()
        if lines and lines[0].strip().startswith(('#', '//')) and 'file' in lines[0].lower():
            return "\n".join(lines[1:]).strip()
        return code.strip()