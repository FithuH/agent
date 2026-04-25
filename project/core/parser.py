"""
core/parser.py
双模解析器：生成时支持 Markdown 提取；调试时支持多文件补丁解析。
"""
import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from utils.logger import setup_logger

logger = setup_logger(__name__)

class FileArtifact:
    def __init__(self, path: str, content: str):
        self.path = Path(path)
        self.content = content

class ResponseParser:
    def extract(self, response: str, expected_filename: Optional[str] = None) -> List[FileArtifact]:
        """【标准生成模式】提取单文件的 Markdown 代码块"""
        blocks = self._extract_markdown_blocks(response)
        if not blocks:
            blocks = [response.strip()]

        artifacts = []
        if expected_filename:
            raw_code = max(blocks, key=len)
            cleaned_code = self._clean_filename_comment(raw_code)
            artifacts.append(FileArtifact(expected_filename, cleaned_code))
        else:
            for block in blocks:
                fname = self._infer_filename(block)
                if fname:
                    cleaned_code = self._clean_filename_comment(block)
                    artifacts.append(FileArtifact(fname, cleaned_code))
        return artifacts

    def extract_with_filenames(self, response: str) -> List[FileArtifact]:
        """【修复自愈模式】提取多个包含 # filename: 注释的代码块"""
        artifacts = []
        blocks = self._extract_markdown_blocks(response)
        
        for block in blocks:
            lines = block.splitlines()
            fname = None
            # 在代码块的前5行寻找文件名标记
            for line in lines[:5]:
                match = re.search(r'#\s*filename:\s*([a-zA-Z0-9_.-]+)', line, re.IGNORECASE)
                if match:
                    fname = match.group(1).strip()
                    break
            
            if fname:
                # 写入代码时，过滤掉我们作为指令的 filename 注释行
                cleaned_lines = [l for l in lines if not re.search(r'#\s*filename:', l, re.IGNORECASE)]
                artifacts.append(FileArtifact(fname, "\n".join(cleaned_lines).strip()))
            else:
                logger.warning("解析补丁时忽略了一个未标记文件名的代码块。")
                
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
        if lines and lines[0].strip().startswith("#") and "file" in lines[0].lower():
            return "\n".join(lines[1:]).strip()
        return code