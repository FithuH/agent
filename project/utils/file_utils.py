import os
from pathlib import Path
from typing import Union

def safe_path(base_dir: Path, sub_path: Union[str, Path]) -> Path:
    """
    防止路径遍历攻击，确保生成的文件在 base_dir 内部。
    """
    base_dir = base_dir.resolve()
    target_path = (base_dir / sub_path).resolve()
    if not str(target_path).startswith(str(base_dir)):
        raise ValueError(f"Attempted to write outside of base directory: {sub_path}")
    return target_path

def write_file(path: Path, content: str, encoding: str = "utf-8") -> None:
    """安全写入文件，自动创建父目录"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)

def copy_template(src: Path, dst: Path) -> None:
    """复制模板文件"""
    import shutil
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)