import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger(__name__)

class FileArtifact:
    """提取的文件内容"""
    def __init__(self, path: str, content: str):
        self.path = Path(path)
        self.content = content

class ResponseParser:
    """从模型响应中提取代码块和文档"""
    
    def __init__(self):
        # 支持的语言扩展名映射
        self.extension_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "html": ".html",
            "css": ".css",
            "json": ".json",
            "yaml": ".yaml",
            "markdown": ".md",
            "bash": ".sh",
            "shell": ".sh",
            "text": ".txt",
        }
    
    def extract(self, response: str) -> List[FileArtifact]:
        """
        从响应中提取所有代码块，并根据语言推断文件名
        """
        artifacts = []
        
        # 匹配 Markdown 代码块: ```language ... ```
        pattern = r"```(\w+)\s*\n(.*?)```"
        matches = re.finditer(pattern, response, re.DOTALL)
        
        for match in matches:
            lang = match.group(1).lower()
            code = match.group(2).strip()
            
            # 尝试从代码内容中推断文件名（如第一行注释包含文件名）
            filename = self._infer_filename(code, lang)
            if filename is None:
                filename = f"generated_{len(artifacts)}{self.extension_map.get(lang, '.txt')}"
            
            artifacts.append(FileArtifact(path=filename, content=code))
            logger.debug(f"Extracted code block: {filename}, language: {lang}")
        
        # 如果没有代码块，尝试将整个响应作为文本文件处理
        if not artifacts:
            logger.warning("No code blocks found, saving entire response as output.txt")
            artifacts.append(FileArtifact(path="output.txt", content=response))
        
        return artifacts
    
    def _infer_filename(self, code: str, lang: str) -> Optional[str]:
        """从代码注释中推断文件名"""
        lines = code.split('\n')
        if not lines:
            return None
        
        first_line = lines[0].strip()
        # 常见注释模式: # filename: main.py 或 // file: app.js
        patterns = [
            r'#\s*filename:\s*(\S+)',
            r'//\s*file:\s*(\S+)',
            r'/\*\s*file:\s*(\S+)\s*\*/',
        ]
        for pattern in patterns:
            match = re.search(pattern, first_line, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # 根据语言给默认名
        if lang in self.extension_map:
            return f"main{self.extension_map[lang]}"
        return None
    
    def extract_readme_sections(self, response: str) -> Dict[str, str]:
        """
        专门提取 README 内容（备用，当前版本未使用）
        """
        # 简化处理，将非代码部分作为说明文本
        # 移除所有代码块
        text = re.sub(r"```.*?```", "", response, flags=re.DOTALL)
        return {"description": text.strip()}