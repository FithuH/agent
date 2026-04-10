import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import ollama
from utils.logger import setup_logger
from utils.validation import validate_json_response

logger = setup_logger(__name__)

class TaskPlan:
    """任务计划数据结构（增强版）"""
    def __init__(self, step: int, filename: str, description: str,
                 dependencies: List[str], exports: List[str], initial_prompt: str):
        self.step = step
        self.filename = filename
        self.description = description
        self.dependencies = dependencies
        self.exports = exports
        self.initial_prompt = initial_prompt

class LocalAgent:
    """本地 Ollama Agent，负责任务规划与动态提示词生成"""

    def __init__(
        self,
        model: str = "qwen2.5:14b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.2,
        system_prompt_path: Optional[Path] = None
    ):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.client = ollama.Client(host=base_url)

        if system_prompt_path is None:
            system_prompt_path = Path(__file__).parent.parent / "templates" / "prompts" / "planner_system.txt"
        self.system_prompt = system_prompt_path.read_text(encoding="utf-8")

    def create_plan(self, requirement: str) -> List[TaskPlan]:
        """将用户需求分解为一系列文件生成任务"""
        logger.info(f"Creating plan for requirement: {requirement[:50]}...")

        user_prompt = f"""
请将以下用户需求分解为具体的文件生成任务列表。

用户需求：
{requirement}

请严格按照系统提示中的 JSON 格式输出。
"""

        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": self.temperature}
        )

        content = response['message']['content']
        logger.debug(f"Agent response: {content[:200]}...")

        data = validate_json_response(content, expected_keys=["tasks"])

        tasks = []
        for task_data in data["tasks"]:
            tasks.append(TaskPlan(
                step=task_data["step"],
                filename=task_data.get("filename", f"file_{task_data['step']}.py"),
                description=task_data["description"],
                dependencies=task_data.get("dependencies", []),
                exports=task_data.get("exports", []),
                initial_prompt=task_data.get("initial_prompt", task_data.get("coder_prompt", ""))
            ))

        logger.info(f"Plan created with {len(tasks)} tasks")
        return tasks

    def generate_file_prompt(self, requirement: str, task: TaskPlan, manifest_summary: str) -> str:
        """
        根据项目状态动态生成针对单个文件的精准提示词。
        此方法调用本地模型，不消耗远程 API token。
        """
        prompt = f"""
你是一位技术架构师。请为远程代码生成模型撰写一个**自包含、精确**的文件生成指令。

项目总需求：{requirement}

当前项目已有文件及接口：
{manifest_summary}

待生成文件：{task.filename}
文件用途：{task.description}
该文件依赖的其他模块：{', '.join(task.dependencies) if task.dependencies else '无'}
该文件需要对外暴露的接口：{', '.join(task.exports) if task.exports else '无'}
初始描述：{task.initial_prompt}

请输出一个完整的指令，包含以下内容：
1. 明确要求生成的文件名（格式：`# filename: {task.filename}`）。
2. 必要的导入语句示例（基于已有模块，若无则写标准库导入）。
3. 每个函数/类的签名、参数、返回值说明。
4. 禁止包含单元测试代码或无关示例。
5. 代码应可直接运行，包含必要的错误处理。

只输出最终指令文本，不要添加额外解释。
"""
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3}
        )
        return response['message']['content'].strip()