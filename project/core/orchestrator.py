import yaml
from pathlib import Path
from typing import List

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
        """DAG 拓扑排序算法：确保被依赖的底层模块优先生成，避免死锁和乱序"""
        graph = {task.filename: task.depends_on for task in tasks}
        task_map = {task.filename: task for task in tasks}
        
        visited = set()
        temp = set()
        order = []
        
        def visit(node):
            if node in temp:
                logger.error(f"严重错误：检测到循环依赖 (Deadlock) 在节点 {node}")
                raise ValueError(f"DAG 死锁: 存在循环依赖 {node}")
            if node not in visited:
                temp.add(node)
                # 遍历它的前置依赖
                for dependency in graph.get(node, []):
                    if dependency in task_map: # 只处理本次计划内的内部文件依赖
                        visit(dependency)
                temp.remove(node)
                visited.add(node)
                order.append(node)
                
        for node in graph:
            if node not in visited:
                visit(node)
                
        # 排序结果返回，此时基石模块（无依赖或依赖已满足的）在列表前面
        return [task_map[node] for node in order]

    def run(self, requirement: str, project_name: str = None, output_dir: str = None) -> Path:
        base_dir = Path(output_dir or self.config["project"].get("default_output_dir", "./output"))
        project_path = self.builder.init_project(project_name or "generated_project", base_dir)
        
        # 1. 获得并行任务规划并进行拓扑重排
        raw_plan: List[TaskPlan] = self.agent.create_plan(requirement)
        try:
            sorted_tasks = self._topological_sort(raw_plan)
            logger.info(f"DAG 拓扑排序完成，生成顺序: {[t.filename for t in sorted_tasks]}")
        except ValueError as e:
            logger.error("拓扑排序失败，降级为原计划顺序。")
            sorted_tasks = raw_plan
            
        manifest = ProjectManifest(project_path)

        # 2. 自底向上生成代码
        for task in sorted_tasks:
            logger.info(f"==> 开始生成文件 [{task.filename}] (依赖项: {task.depends_on})")
            
            # 【核心架构改变】：使用 JIT 精准注入，只给当前文件需要的 AST 契约
            jit_context = manifest.get_jit_context(task.depends_on)
            
            # 组装最终发给 DeepSeek 的系统级 Prompt
            sys_prompt = f"""你是一个顶级的 Python 架构师和 Coder。
当前任务: 生成 {task.filename}。
需求描述: {task.coder_prompt}

{jit_context}

要求：
1. 你的代码必须完整，不要省略，可以直接运行。
2. 你必须且只能使用上述《接口契约》中列出的函数和类，不得自行脑补尚未创建的接口。
3. 请使用 Markdown 格式返回代码，并加上 ```python 标签。
"""
            response = self.remote.generate(prompt=sys_prompt)
            artifacts = self.parser.extract(response, expected_filename=task.filename)
            self.builder.write_files(artifacts)
            
            # 将生成的代码解析为 AST 契约，写入 Manifest 供下游使用
            for art in artifacts:
                manifest.update_file(art.path.name, art.content, task.description)

        # 这里保留你的自愈调试逻辑，流程基本不变
        # self._run_debugger(project_path, sorted_tasks, manifest)
        
        logger.info("代码自底向上生成完毕。")
        return project_path