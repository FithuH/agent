import yaml
import re
import ast
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Set

from core.agent import LocalAgent, TaskPlan
from core.remote_api import RemoteAPIClient
from core.parser import ResponseParser, FileArtifact
from core.builder import ProjectBuilder
from core.context_manager import ProjectManifest
from utils.file_utils import write_file
from utils.logger import setup_logger

logger = setup_logger(__name__)


class Orchestrator:
    # 常见 import 到 PyPI 包名的映射
    IMPORT_TO_PACKAGE = {
        "pygame": "pygame",
        "numpy": "numpy",
        "pandas": "pandas",
        "requests": "requests",
        "flask": "Flask",
        "django": "Django",
        "tensorflow": "tensorflow",
        "torch": "torch",
        "PIL": "Pillow",
        "cv2": "opencv-python",
        "bs4": "beautifulsoup4",
        "yaml": "PyYAML",
        "dotenv": "python-dotenv",
        "pytest": "pytest",
    }

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.parser = ResponseParser()
        self.builder = ProjectBuilder()

        self.agent = LocalAgent(
            model=self.config["ollama"]["model"],
            base_url=self.config["ollama"]["base_url"],
            temperature=self.config["ollama"]["temperature"]
        )
        self.remote = RemoteAPIClient(
            model=self.config["deepseek"]["model"],
            temperature=self.config["deepseek"]["temperature"],
            max_tokens=self.config["deepseek"]["max_tokens"]
        )

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def run(self, requirement: str, project_name: str = None, output_dir: str = None) -> Path:
        logger.info(f"开始生成项目: {requirement}")

        plan: List[TaskPlan] = self.agent.create_plan(requirement)
        actual_name = project_name or self._gen_name(requirement)
        base_dir = Path(output_dir or self.config["project"].get("default_output_dir", "./output"))
        project_path = self.builder.init_project(actual_name, base_dir)

        manifest = ProjectManifest(project_path)

        for idx, task in enumerate(plan):
            logger.info(f"生成文件 {idx+1}/{len(plan)}: {task.filename} - {task.description}")

            summary = manifest.get_progress_summary()
            precise_prompt = self.agent.generate_file_prompt(
                requirement=requirement,
                task=task,
                manifest_summary=summary
            )
            logger.debug(f"精准提示词 (前200字符): {precise_prompt[:200]}...")

            response = self.remote.generate(precise_prompt)
            artifacts = self.parser.extract(response)

            for art in artifacts:
                if art.path.name != task.filename and not art.path.name.startswith("generated"):
                    art.path = Path(task.filename)
                if art.path.name.startswith("test_") and (project_path / art.path.name.replace("test_", "")).exists():
                    art.path = Path("test_" + art.path.name)

                self.builder.write_files([art])
                desc = self.parser.text_fragments[0] if self.parser.text_fragments else task.description
                manifest.update_file(art.path.name, art.content, desc)
                logger.debug(f"已写入: {art.path.name}")

            self.parser.text_fragments.clear()

        # 后处理：智能补充依赖
        self._ensure_requirements(project_path, requirement)

        # 后处理：确保主文件有效
        self._ensure_main_file_valid(project_path, requirement)

        # 后处理：生成隔离的启动脚本
        self._generate_isolated_run_scripts(project_path)

        self.builder.finalize(project_path, generate_readme=True)
        logger.info(f"项目生成完成: {project_path}")
        return project_path

    def _ensure_requirements(self, project_path: Path, requirement: str):
        """智能生成 requirements.txt：优先调用 API，失败则自动扫描代码导入"""
        req_file = project_path / "requirements.txt"
        if req_file.exists() and req_file.stat().st_size > 10:
            return

        logger.info("正在生成 requirements.txt...")
        # 尝试调用远程 API 生成
        prompt = f"根据项目需求 '{requirement}'，列出所需的 Python 包及其版本（如 pygame==2.5.2）。格式：`# filename: requirements.txt`。"
        resp = self.remote.generate(prompt)
        arts = self.parser.extract(resp)
        for art in arts:
            if art.path.name == "requirements.txt" and art.content.strip():
                write_file(req_file, art.content)
                logger.info("已通过 API 生成 requirements.txt")
                return

        # 回退：扫描项目中的所有 .py 文件，提取导入
        packages = self._scan_imports(project_path)
        if packages:
            content = "\n".join(sorted(packages))
            write_file(req_file, content)
            logger.info(f"已通过代码扫描生成 requirements.txt，包含 {len(packages)} 个包")
        else:
            req_file.write_text("# No external dependencies detected\n")
            logger.warning("未检测到外部依赖，requirements.txt 留空")

    def _scan_imports(self, project_path: Path) -> Set[str]:
        """递归扫描所有 .py 文件，提取标准库外的导入并映射到包名"""
        packages = set()
        stdlib = self._get_stdlib_modules()

        for py_file in project_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding='utf-8')
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            pkg = alias.name.split('.')[0]
                            if pkg not in stdlib:
                                packages.add(self.IMPORT_TO_PACKAGE.get(pkg, pkg))
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            pkg = node.module.split('.')[0]
                            if pkg not in stdlib:
                                packages.add(self.IMPORT_TO_PACKAGE.get(pkg, pkg))
            except Exception as e:
                logger.debug(f"解析文件 {py_file} 时出错: {e}")
        return packages

    def _get_stdlib_modules(self) -> Set[str]:
        """返回 Python 标准库模块名集合（简化版）"""
        import sys
        return set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else set()

    def _ensure_main_file_valid(self, project_path: Path, requirement: str):
        main_py = project_path / "main.py"
        if main_py.exists():
            content = main_py.read_text(encoding='utf-8')
            if "import unittest" in content or "class Test" in content:
                logger.warning("main.py 包含测试代码，将重新生成...")
                main_py.unlink()
        if not main_py.exists():
            prompt = f"生成项目主入口 main.py。需求：{requirement}。格式：`# filename: main.py`。"
            resp = self.remote.generate(prompt)
            arts = self.parser.extract(resp)
            for art in arts:
                if art.path.name == "main.py":
                    write_file(main_py, art.content)
                    logger.info("已生成 main.py")
                    return

    def _generate_isolated_run_scripts(self, project_path: Path):
        """生成使用项目内隔离虚拟环境的启动脚本"""
        main_file = self._find_main_py(project_path) or "main.py"
        venv_dir = ".venv_generated"  # 使用隐藏目录，避免与外层 venv 冲突

        run_sh = project_path / "run.sh"
        if not run_sh.exists():
            content = f"""#!/bin/bash
# 自动创建项目独立虚拟环境并运行
if [ ! -d "{venv_dir}" ]; then
    python3 -m venv {venv_dir}
fi
source {venv_dir}/bin/activate
if [ -s requirements.txt ]; then
    pip install -r requirements.txt
else
    echo "警告: requirements.txt 为空，请手动安装依赖"
fi
python {main_file}
"""
            write_file(run_sh, content)
            run_sh.chmod(0o755)
            logger.info(f"已生成 run.sh (虚拟环境: {venv_dir})")

        run_bat = project_path / "run.bat"
        if not run_bat.exists():
            content = f"""@echo off
REM 自动创建项目独立虚拟环境并运行
if not exist "{venv_dir}" (
    python -m venv {venv_dir}
)
call {venv_dir}\\Scripts\\activate.bat
if exist requirements.txt (
    for %%I in (requirements.txt) do if %%~zI gtr 0 (
        pip install -r requirements.txt
    ) else (
        echo 警告: requirements.txt 为空，请手动安装依赖
    )
) else (
    echo 警告: 未找到 requirements.txt，请手动安装依赖
)
python {main_file}
"""
            write_file(run_bat, content)
            logger.info(f"已生成 run.bat (虚拟环境: {venv_dir})")

    def _find_main_py(self, project_path: Path) -> Optional[str]:
        for name in ["main.py", "app.py", "run.py", "game.py"]:
            if (project_path / name).exists():
                return name
        for f in project_path.glob("*.py"):
            return f.name
        return None

    def _gen_name(self, requirement: str) -> str:
        base = "_".join(requirement.lower().split()[:3])
        return re.sub(r'[^\w\-_]', '', base) + "_project"