import ast
import sys
from pathlib import Path
from typing import Set

class DependencyScanner:
    IMPORT_TO_PACKAGE = {
        "cv2": "opencv-python", "yaml": "PyYAML", "PIL": "Pillow",
        "bs4": "beautifulsoup4", "dotenv": "python-dotenv", "pygame": "pygame"
    }

    def __init__(self):
        self.stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else {"os", "sys", "time"}

    def scan_project(self, project_dir: Path) -> Set[str]:
        packages: Set[str] = set()
        # 动态收集本地生成的文件名（如 config, logic），防止被当做第三方库
        local_modules = {f.stem for f in project_dir.glob("*.py")}
        
        for py_file in project_dir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self._add_pkg(packages, alias.name, local_modules)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        self._add_pkg(packages, node.module, local_modules)
            except Exception:
                pass
        return packages

    def _add_pkg(self, pkgs: Set[str], import_name: str, local_modules: Set[str]):
        pkg = import_name.split('.')[0]
        if pkg not in self.stdlib and pkg not in local_modules and not pkg.startswith("_"):
            pkgs.add(self.IMPORT_TO_PACKAGE.get(pkg, pkg))