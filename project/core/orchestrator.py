import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from core.agent import LocalAgent
from core.remote_api import RemoteAPIClient
from core.parser import ResponseParser, FileArtifact
from core.builder import ProjectBuilder
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Orchestrator:
    """主流程协调器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self._setup_logging()
        
        # 初始化组件
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
        self.parser = ResponseParser()
        self.builder = ProjectBuilder()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _setup_logging(self):
        log_level = self.config.get("logging", {}).get("level", "INFO")
        log_file = self.config.get("logging", {}).get("file")
        # 日志已在各模块初始化时设置，此处无需重复
        # 但可以调整根日志级别
        import logging
        logging.getLogger("forge").setLevel(log_level)
    
    def run(
        self,
        requirement: str,
        project_name: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Path:
        """
        执行完整的项目生成流程
        """
        # 确定项目名称
        if not project_name:
            # 简单生成名称：取需求前几个词，转小写，替换空格为下划线
            words = requirement.lower().split()
            project_name = "_".join(words[:3]) + "_project"
            # 移除特殊字符
            import re
            project_name = re.sub(r'[^\w\-_]', '', project_name)
        
        # 确定输出目录
        if output_dir is None:
            output_dir = self.config["project"]["default_output_dir"]
        base_dir = Path(output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Starting project generation: {project_name}")
        logger.info(f"Requirement: {requirement}")
        
        # Step 1: 本地 Agent 规划
        logger.info("Step 1: Planning with local agent...")
        plan = self.agent.create_plan(requirement)
        
        # Step 2: 初始化项目目录
        logger.info("Step 2: Initializing project directory...")
        project_path = self.builder.init_project(project_name, base_dir)
        
        # Step 3: 循环执行每个任务
        for task in plan:
            logger.info(f"Step 3.{task.step}: {task.description}")
            logger.debug(f"Coder prompt: {task.coder_prompt[:100]}...")
            
            # 调用远程 API 生成代码
            response = self.remote.generate(task.coder_prompt)
            
            # 解析响应，提取文件
            artifacts = self.parser.extract(response)
            
            # 写入文件
            self.builder.write_files(artifacts)
        
        # Step 4: 收尾工作
        logger.info("Step 4: Finalizing project...")
        auto_readme = self.config["project"].get("auto_create_readme", True)
        self.builder.finalize(project_path, generate_readme=auto_readme)
        
        # 可选：Git 初始化
        if self.config["project"].get("git_init", False):
            self._git_init(project_path)
        
        logger.info(f"Project successfully generated at: {project_path}")
        return project_path
    
    def _git_init(self, project_path: Path):
        """初始化 Git 仓库"""
        import subprocess
        try:
            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            logger.info("Git repository initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize git: {e}")