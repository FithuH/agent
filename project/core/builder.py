import shutil
from pathlib import Path
from typing import List, Optional
from core.parser import FileArtifact
from utils.file_utils import safe_path, write_file, copy_template
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ProjectBuilder:
    """负责在文件系统中创建项目结构"""
    
    def __init__(self, templates_dir: Optional[Path] = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent / "templates" / "project_skel"
        self.templates_dir = templates_dir
        self.current_project_path: Optional[Path] = None
    
    def init_project(self, name: str, base_dir: Path) -> Path:
        project_path = safe_path(base_dir, name)
        if project_path.exists():
            logger.warning(f"Project directory already exists: {project_path}")
        project_path.mkdir(parents=True, exist_ok=True)
        self.current_project_path = project_path
        logger.info(f"Project initialized at: {project_path}")
        return project_path
    
    def write_files(self, artifacts: List[FileArtifact]) -> None:
        if not self.current_project_path:
            raise RuntimeError("Project not initialized. Call init_project first.")
        
        for artifact in artifacts:
            target_path = safe_path(self.current_project_path, artifact.path)
            write_file(target_path, artifact.content)
            logger.info(f"Written: {target_path.relative_to(self.current_project_path)}")
    
    def finalize(self, project_path: Path, generate_readme: bool = True) -> None:
        """
        完成项目构建：仅复制模板文件。
        注意：requirements.txt 现在由 Orchestrator 的 AST Scanner 精确生成。
        """
        if self.templates_dir.exists():
            for item in self.templates_dir.iterdir():
                if item.is_file():
                    dest = project_path / item.name
                    if not dest.exists():
                        copy_template(item, dest)
                        logger.info(f"Copied template: {item.name}")