import json
import ast
from pathlib import Path
from typing import List, Dict, Any
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ProjectManifest:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.manifest_path = project_path / ".forge_manifest.json"
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"project": str(self.project_path), "files": {}}

    def _save(self):
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def update_file(self, filename: str, content: str, description: str):
        """更新文件清单，并精准提取 AST 代码骨架"""
        skeleton = self._extract_skeleton(content)
        if "files" not in self.data:
            self.data["files"] = {}
            
        self.data["files"][filename] = {
            "description": description,
            "skeleton": skeleton,
            "size": len(content)
        }
        self._save()

    def _extract_skeleton(self, content: str) -> str:
        """高级 AST 语法树提取：保留函数签名和类结构"""
        try:
            tree = ast.parse(content)
        except Exception:
            return "语法解析失败，无法提供骨架"
            
        lines = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        lines.append(f"{target.id} = ...")
            elif isinstance(node, ast.ClassDef):
                lines.append(f"class {node.name}:")
                has_content = False
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef):
                        try:
                            # Python 3.9+ 支持 unparse
                            args_str = ast.unparse(sub.args)
                            ret_str = f" -> {ast.unparse(sub.returns)}" if sub.returns else ""
                            lines.append(f"    def {sub.name}({args_str}){ret_str}: ...")
                            has_content = True
                        except AttributeError:
                            lines.append(f"    def {sub.name}(...): ...")
                            has_content = True
                if not has_content:
                    lines.append("    pass")
            elif isinstance(node, ast.FunctionDef):
                try:
                    args_str = ast.unparse(node.args)
                    ret_str = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                    lines.append(f"def {node.name}({args_str}){ret_str}: ...")
                except AttributeError:
                    lines.append(f"def {node.name}(...): ...")
                    
        return "\n".join(lines) if lines else "该文件暂无暴露的类或函数。"

    def get_jit_context(self, depends_on: List[str]) -> str:
        """核心方法：JIT 精准契约注入"""
        if not depends_on:
            return "# 当前模块无本地依赖。"

        context = ["【重要契约：你必须且只能调用以下已存在的接口】"]
        for dep in depends_on:
            file_info = self.data.get("files", {}).get(dep)
            if file_info:
                context.append(f"\n--- 文件: {dep} ---")
                context.append(file_info['skeleton'])
            else:
                context.append(f"\n--- 文件: {dep} (暂无可用接口) ---")
        
        return "\n".join(context)

    def get_progress_summary(self) -> str:
        if "files" not in self.data: return "无"
        return ", ".join(self.data["files"].keys())