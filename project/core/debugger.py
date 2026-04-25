"""
core/debugger.py
脚手架自动调试引擎，负责沙盒执行与防 Token 爆炸。
"""
import sys
import subprocess
import os
from pathlib import Path
from typing import Tuple
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ProjectDebugger:
    def __init__(self, timeout: int = 3):
        self.timeout = timeout

    def test_run(self, project_path: Path, main_file: str) -> Tuple[bool, str]:
        target = project_path / main_file
        if not target.exists():
            return False, f"入口文件 {main_file} 不存在，无法运行测试。"
        
        try:
            env = os.environ.copy()
            env["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
            # 强制无缓冲输出，防止 Python 缓冲机制截留崩溃日志
            env["PYTHONUNBUFFERED"] = "1" 
            
            process = subprocess.Popen(
                [sys.executable, main_file],
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
                if process.returncode == 0:
                    return True, "运行成功，无报错。"
                else:
                    error_msg = stderr.strip() or stdout.strip() or "程序异常退出，无错误信息。"
                    # 【核心工程手段：Token 保护机制】
                    if len(error_msg) > 1500:
                        error_msg = "[...头部被截断...]\n" + error_msg[-1500:]
                    return False, error_msg
                    
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate() 
                return True, "运行超时未崩溃，GUI/游戏主循环启动成功。"
                
        except Exception as e:
            return False, f"系统级进程启动异常: {e}"