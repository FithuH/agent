import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import ollama
from utils.logger import setup_logger
from utils.validation import validate_json_response

logger = setup_logger(__name__)

class TaskPlan:
    """任务计划数据结构"""
    def __init__(self, step: int, description: str, coder_prompt: str):
        self.step = step
        self.description = description
        self.coder_prompt = coder_prompt

class LocalAgent:
    """本地 Ollama Agent，负责任务规划"""
    
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
        
        # 加载系统提示词模板
        if system_prompt_path is None:
            system_prompt_path = Path(__file__).parent.parent / "templates" / "prompts" / "planner_system.txt"
        self.system_prompt = system_prompt_path.read_text(encoding="utf-8")
    
    def create_plan(self, requirement: str) -> List[TaskPlan]:
        """
        将用户需求分解为一系列开发任务
        """
        logger.info(f"Creating plan for requirement: {requirement[:50]}...")
        
        user_prompt = f"""
请将以下用户需求分解为具体的开发任务列表。

用户需求：
{requirement}

请严格按照 JSON 格式输出，格式如下：
{{
  "tasks": [
    {{
      "step": 1,
      "description": "任务简要描述",
      "coder_prompt": "给代码生成模型的详细提示词，包含技术要求、注意事项等"
    }},
    ...
  ]
}}

要求：
1. 每个 coder_prompt 必须足够详细，使得代码生成模型能直接写出可运行的代码。
2. 任务应按逻辑顺序排列，每个任务专注于一个文件或一个功能模块。
3. 考虑必要的依赖、配置文件。
4. 最后一步应生成 README.md 文件。
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
        
        # 验证并解析 JSON
        data = validate_json_response(content, expected_keys=["tasks"])
        
        tasks = []
        for task_data in data["tasks"]:
            tasks.append(TaskPlan(
                step=task_data["step"],
                description=task_data["description"],
                coder_prompt=task_data["coder_prompt"]
            ))
        
        logger.info(f"Plan created with {len(tasks)} steps")
        return tasks