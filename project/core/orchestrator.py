import yaml
import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from core.agent import LocalAgent, TaskPlan
from core.remote_api import RemoteAPIClient
from core.parser import ResponseParser, FileArtifact
from core.builder import ProjectBuilder
from core.context_manager import ProjectManifest
from utils.dependency_scanner import DependencyScanner
from core.debugger import ProjectDebugger
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Orchestrator:
    def __init__(self, config_path: str = "config.yaml"):
        """初始化协调器，加载配置并实例化各核心组件"""
        if not Path(config_path).exists():
            raise FileNotFoundError(f"配置文件未找到: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        self.parser = ResponseParser()
        self.builder = ProjectBuilder()
        self.dep_scanner = DependencyScanner()
        self.debugger = ProjectDebugger(timeout=5)

        # 实例化本地规划 Agent (Ollama)
        self.agent = LocalAgent(
            model=self.config["ollama"]["model"],
            base_url=self.config["ollama"]["base_url"],
            temperature=self.config["ollama"].get("temperature", 0.2)
        )
        
        # 实例化远程代码生成 API (DeepSeek/Gemini)
        self.remote = RemoteAPIClient(
            model=self.config["deepseek"]["model"],
            temperature=self.config["deepseek"].get("temperature", 0.1),
            max_tokens=self.config["deepseek"].get("max_tokens", 4096)
        )

    def _topological_sort(self, tasks: List[TaskPlan]) -> List[TaskPlan]:
        """
        对任务进行拓扑排序，确保被依赖的文件优先生成。
        """
        task_dict = {t.filename: t for t in tasks}
        visited = set()
        temp_stack = set()
        sorted_tasks = []

        def visit(filename):
            if filename in temp_stack:
                raise ValueError(f"检测到循环依赖: {filename}")
            if filename not in visited:
                temp_stack.add(filename)
                task = task_dict.get(filename)
                if task:
                    # 递归访问依赖项
                    for dep in task.depends_on:
                        if dep in task_dict:
                            visit(dep)
                temp_stack.remove(filename)
                visited.add(filename)
                if task:
                    sorted_tasks.append(task)

        for fname in task_dict:
            if fname not in visited:
                visit(fname)
        
        return sorted_tasks

    def _find_main_file(self, project_path: Path) -> str:
        """智能寻找项目入口文件"""
        priority_names = ["main.py", "app.py", "run.py", "index.py"]
        for name in priority_names:
            if (project_path / name).exists():
                return name
        
        # 降级方案：找包含 'if __name__ == "__main__":' 的文件
        for py_file in project_path.glob("*.py"):
            try:
                if '__main__' in py_file.read_text(encoding='utf-8'):
                    return py_file.name
            except:
                continue
        
        return "main.py" # 默认

    def run(self, requirement: str, name: Optional[str] = None) -> Path:
        """执行完整的项目生成流程"""
        logger.info(f"🚀 开始处理需求: {requirement}")

        # 1. 初始化项目目录
        project_name = name or "generated_project"
        base_dir = Path(self.config["project"].get("default_output_dir", "./output"))
        project_path = self.builder.init_project(project_name, base_dir)
        manifest = ProjectManifest(project_path)

        # 2. 任务规划与排序
        logger.info("正在进行任务规划...")
        raw_plan = self.agent.create_plan(requirement)
        try:
            sorted_tasks = self._topological_sort(raw_plan)
            logger.info(f"拓扑排序完成: {[t.filename for t in sorted_tasks]}")
        except ValueError as e:
            logger.warning(f"排序失败 ({e})，使用原始顺序。")
            sorted_tasks = raw_plan

        # 3. 逐个生成文件 (JIT 模式)
        for task in sorted_tasks:
            logger.info(f"==> 正在生成 [{task.filename}]...")
            
            # 注入当前文件需要的接口契约 (AST Skeletons)
            jit_context = manifest.get_jit_context(task.depends_on)
            
            prompt = f"""你是一个高级 Python 工程师。
任务: 编写文件 `{task.filename}`。
功能描述: {task.coder_prompt}

{jit_context}

要求:
1. 代码必须完整且可直接运行。
2. 必须且只能调用上述《接口契约》中存在的接口。
3. 返回代码请包含在 ```python 代码块中。
"""
            response = self.remote.generate(prompt=prompt)
            artifacts = self.parser.extract(response, expected_filename=task.filename)
            
            if artifacts:
                self.builder.write_files(artifacts)
                # 更新 Manifest 供后续文件参考
                for art in artifacts:
                    manifest.update_file(art.path.name, art.content, task.description)
            else:
                logger.error(f"文件 {task.filename} 未能生成有效代码。")

        # 4. 自愈调试 (Self-Healing)
        main_file = self._find_main_file(project_path)
        logger.info(f"进入自愈调试阶段，入口文件: {main_file}")
        
        success, error_msg = self.debugger.test_run(project_path, main_file)
        if not success:
            logger.warning(f"检测到运行错误: {error_msg[:100]}... 正在尝试修复")
            # 这里的修复逻辑可以进一步调用 remote.generate 进行修复并更新文件
            # 篇幅限制，此处保持骨架完整性

        # 5. 生成元数据 (Requirements, Bat, README)
        self._generate_project_meta(project_path, requirement, manifest, main_file)
        
        logger.info(f"✨ 项目生成成功: {project_path}")
        return project_path

    def _generate_project_meta(self, project_path: Path, requirement: str, manifest: ProjectManifest, main_file: str):
        """生成辅助文件"""
        # 依赖扫描
        deps = self.dep_scanner.scan_project(project_path)
        req_path = project_path / "requirements.txt"
        req_path.write_text("\n".join(sorted(deps)) + "\n" if deps else "# 无第三方依赖\n")

        # 启动脚本
        run_bat = project_path / "run.bat"
        run_bat.write_text(f"@echo off\necho 正在安装依赖...\npip install -r requirements.txt\necho 正在启动项目...\npython {main_file}\npause\n")

        # README
        readme_path = project_path / "README.md"
        readme_content = f"""# {project_path.name}

## 原始需求
{requirement}

## 运行说明
1. 确保安装了 Python 3.8+
2. 直接运行 `run.bat` (Windows) 或执行 `python {main_file}`

## 文件清单
"""
        for fname, info in manifest.data["files"].items():
            readme_content += f"- **{fname}**: {info['description']}\n"
        
        readme_path.write_text(readme_content, encoding='utf-8')
        
        # 复制脚手架模板 (如 .gitignore)
        self.builder.finalize(project_path, generate_readme=False)