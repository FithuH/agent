import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from core.agent import LocalAgent, TaskPlan
from core.remote_api import RemoteAPIClient
from core.parser import ResponseParser
from core.builder import ProjectBuilder
from core.context_manager import ProjectManifest
from utils.logger import setup_logger

logger = setup_logger(__name__)


class Orchestrator:
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
        logger.info(f"Starting project generation: {requirement}")

        # 1. 任务规划
        plan: List[TaskPlan] = self.agent.create_plan(requirement)

        # 2. 初始化目录
        actual_name = project_name or self._gen_default_name(requirement)
        base_dir = Path(output_dir or self.config["project"].get("default_output_dir", "./output"))
        project_path = self.builder.init_project(actual_name, base_dir)

        # 3. 初始化项目清单与内存上下文
        manifest = ProjectManifest(project_path)
        memory_context = {}  # 文件名 -> 内容

        # 4. 执行每个子任务
        for idx, task in enumerate(plan):
            logger.info(f"Step {idx+1}/{len(plan)}: {task.description}")

            # 构造增强提示词
            system_note = f"""
你是全栈工程师，根据任务生成代码。

{manifest.get_progress_summary()}

规则：
- 每个代码块首行注释 `# filename: 文件名`
- 不要生成单元测试代码到主文件
- 确保新代码与已有文件正确协作
"""
            history = "\n".join([
                f"### {name}\n```\n{content}\n```"
                for name, content in memory_context.items()
            ])
            full_prompt = f"{system_note}\n\n已有代码：\n{history}\n\n当前任务：\n{task.coder_prompt}"

            # 调用远程 API
            response = self.remote.generate(full_prompt)
            artifacts = self.parser.extract(response)

            for art in artifacts:
                # 更新内存和清单
                memory_context[art.path.name] = art.content
                # 取解析器收集的第一段文本作为描述
                desc = self.parser.text_fragments[0] if self.parser.text_fragments else ""
                manifest.update_file(art.path.name, art.content, desc)

            self.builder.write_files(artifacts)
            self.parser.text_fragments.clear()

        # 5. 收尾
        self.builder.finalize(project_path, generate_readme=True)
        logger.info(f"Project generated at: {project_path}")
        return project_path

    def _gen_default_name(self, requirement: str) -> str:
        import re
        base = "_".join(requirement.lower().split()[:3])
        return re.sub(r'[^\w\-_]', '', base) + "_project"