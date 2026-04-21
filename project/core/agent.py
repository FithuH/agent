import json
import re
from pathlib import Path
from typing import List
import ollama
from utils.logger import setup_logger

logger = setup_logger(__name__)

class TaskPlan:
    def __init__(self, step: int, filename: str, description: str, coder_prompt: str, depends_on: List[str] = None):
        self.step = step
        self.filename = filename
        self.description = description
        self.coder_prompt = coder_prompt
        # [核心增强]：维护有向无环图 (DAG) 的前置依赖
        self.depends_on = depends_on or []

class LocalAgent:
    def __init__(self, model: str = "qwen2.5:14b", base_url: str = "http://localhost:11434", temperature: float = 0.2):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.client = ollama.Client(host=base_url)
        
        system_prompt_path = Path(__file__).parent.parent / "templates" / "prompts" / "planner_system.txt"
        with open(system_prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()

    def create_plan(self, requirement: str) -> List[TaskPlan]:
        logger.info(f"正在构建项目 DAG 并规划需求: {requirement}")
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": requirement}
            ],
            options={"temperature": self.temperature},
            format="json"
        )
        
        try:
            plan_data = json.loads(response['message']['content'])
            tasks = []
            for task_data in plan_data.get("tasks", []):
                fname = task_data.get("filename", "").strip()
                if not fname or fname.startswith("module_") or fname.startswith("file_"):
                    match = re.search(r'([a-zA-Z0-9_]+\.py)', task_data.get("coder_prompt", ""))
                    fname = match.group(1) if match else f"core_logic_{task_data['step']}.py"
                
                tasks.append(TaskPlan(
                    step=task_data["step"],
                    filename=fname,
                    description=task_data.get("description", ""),
                    coder_prompt=task_data.get("coder_prompt", ""),
                    depends_on=task_data.get("depends_on", [])  # 提取依赖树
                ))
            return tasks
        except json.JSONDecodeError as e:
            logger.error(f"Planner JSON 解析崩溃: {e}\n原文: {response['message']['content']}")
            raise RuntimeError("LocalAgent 无法生成合法的 JSON DAG")