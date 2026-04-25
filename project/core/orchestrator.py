import yaml
import os
from pathlib import Path
from typing import List, Optional

from core.agent import LocalAgent, TaskPlan
from core.remote_api import RemoteAPIClient
from core.parser import ResponseParser
from core.builder import ProjectBuilder
from core.context_manager import ProjectManifest
from utils.dependency_scanner import DependencyScanner
from core.debugger import ProjectDebugger
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Orchestrator:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        self.parser = ResponseParser()
        self.builder = ProjectBuilder()
        self.dep_scanner = DependencyScanner()
        self.debugger = ProjectDebugger(timeout=self.config.get("project", {}).get("test_timeout", 5))

        self.agent = LocalAgent(
            model=self.config["ollama"]["model"],
            base_url=self.config["ollama"]["base_url"]
        )
        self.remote = RemoteAPIClient(
            model=self.config["deepseek"]["model"],
            temperature=self.config["deepseek"]["temperature"],
            max_tokens=self.config["deepseek"]["max_tokens"]
        )

    def _topological_sort(self, tasks: List[TaskPlan]) -> List[TaskPlan]:
        """DAG 拓扑排序：确保被依赖的底层模块优先生成"""
        task_dict = {t.filename: t for t in tasks}
        visited = set()
        stack = set()
        results = []

        def visit(filename):
            if filename in stack:
                raise ValueError(f"检测到循环依赖: {filename}")
            if filename in visited:
                return
            
            task = task_dict.get(filename)
            if not task: 
                return

            stack.add(filename)
            for dep in task.depends_on:
                visit(dep)
            stack.remove(filename)
            visited.add(filename)
            results.append(task)

        for t in tasks:
            visit(t.filename)
        return results

    def _find_main_file(self, project_path: Path) -> Optional[str]:
        """智能寻找入口文件"""
        for name in ["main.py", "app.py", "run.py", "game.py", "index.py"]:
            if (project_path / name).exists():
                return name
        py_files = [f.name for f in project_path.glob("*.py") if f.name not in ["config.py", "utils.py"]]
        return py_files[0] if py_files else None

    def _fix_project(self, project_path: Path, main_file: str, error_msg: str, manifest: ProjectManifest) -> bool:
        """自愈核心：通过 Traceback 让 LLM 生成补丁"""
        logger.warning(f"🛠️ 启动自愈模式。错误摘要: {error_msg[:100]}...")
        
        prompt_path = Path(__file__).parent.parent / "templates" / "prompts" / "fixer_system.txt"
        fixer_sys = prompt_path.read_text(encoding='utf-8') if prompt_path.exists() else "你是一个顶级 Python 修复专家。"

        # 构造上下文：报错 + 全局已生成文件的骨架契约
        all_files = list(manifest.data.get("files", {}).keys())
        global_context = manifest.get_jit_context(all_files)
        
        context = f"项目路径: {project_path}\n入口文件: {main_file}\n\n【运行时报错】\n{error_msg}\n\n【当前项目全局契约】\n{global_context}"
        prompt = f"{fixer_sys}\n\n请分析并修复上述错误，必须按规范输出补丁：\n{context}"

        response = self.remote.generate(prompt=prompt)
        
        # 提取带有 # filename: 标记的修复代码块
        fix_artifacts = self.parser.extract_with_filenames(response)
        
        if fix_artifacts:
            logger.info(f"成功解析并应用了 {len(fix_artifacts)} 个修复补丁...")
            self.builder.write_files(fix_artifacts)
            for art in fix_artifacts:
                manifest.update_file(art.path.name, art.content, "Bug Fix (Self-healing)")
            return True
        return False

    def run(self, requirement: str, name: Optional[str] = None) -> Path:
        project_name = name or "generated_project"
        output_dir = Path("./output")
        logger.info(f"🚀 开始任务，项目名称: {project_name}")
        
        project_path = self.builder.init_project(project_name, output_dir)
        manifest = ProjectManifest(project_path)

        # 1. 规划阶段
        raw_plan = self.agent.create_plan(requirement)
        try:
            sorted_tasks = self._topological_sort(raw_plan)
        except ValueError as e:
            logger.error(f"拓扑排序失败: {e}，将降级使用原始顺序。")
            sorted_tasks = raw_plan

        # 2. 生成阶段
        for task in sorted_tasks:
            logger.info(f"==> 正在生成: {task.filename}")
            jit_context = manifest.get_jit_context(task.depends_on)
            sys_prompt = f"任务: 生成 {task.filename}\n描述: {task.coder_prompt}\n\n{jit_context}\n\n请返回完整代码。"
            
            response = self.remote.generate(prompt=sys_prompt)
            artifacts = self.parser.extract(response, expected_filename=task.filename)
            self.builder.write_files(artifacts)
            for art in artifacts:
                manifest.update_file(art.path.name, art.content, task.description)

        # 3. 调试与自愈阶段 (最多 3 次尝试)
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            main_file = self._find_main_file(project_path)
            if not main_file:
                logger.warning("未找到标准入口文件，跳过自动化测试闭环。")
                break
                
            success, error_msg = self.debugger.test_run(project_path, main_file)
            if success:
                logger.info("✅ 自动化测试完美通过！无报错。")
                break
            else:
                if attempt < MAX_RETRIES - 1:
                    if not self._fix_project(project_path, main_file, error_msg, manifest):
                        logger.error("大模型未能输出有效补丁格式，自愈中断。")
                        break
                else:
                    logger.error("达到最大重试次数，自愈结束。")

        # 4. 收尾阶段
        self._finalize(project_path, main_file)
        return project_path

    def _finalize(self, project_path: Path, main_file: Optional[str]):
        deps = self.dep_scanner.scan_project(project_path)
        (project_path / "requirements.txt").write_text(
            "\n".join(sorted(deps)) if deps else "# 无第三方依赖", encoding="utf-8"
        )
        if main_file:
            run_script = "python" if os.name != 'nt' else "python"
            (project_path / "run_project.sh").write_text(f"pip install -r requirements.txt\n{run_script} {main_file}")
            
        logger.info(f"✨ 项目已就绪: {project_path.absolute()}")