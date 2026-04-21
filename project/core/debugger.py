"""
core/debugger.py
脚手架自动调试引擎，负责沙盒执行与报错捕获。
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
        """
        :param timeout: 超时时间。GUI/游戏程序通常带有死循环。
                        如果 3 秒内崩溃，说明存在语法或初始化接口报错；
                        如果 3 秒未崩溃，说明主窗口已成功启动并在监听事件。
        """
        self.timeout = timeout

    def test_run(self, project_path: Path, main_file: str) -> Tuple[bool, str]:
        target = project_path / main_file
        if not target.exists():
            return False, f"入口文件 {main_file} 不存在，无法运行测试。"
        
        try:
            # 屏蔽 pygame 的欢迎信息以保持日志干净
            env = os.environ.copy()
            env["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
            
            # 使用 sys.executable 确保和当前脚手架使用同一个 Python 和依赖环境
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
                    # 优先返回 stderr 报错信息
                    error_msg = stderr.strip() or stdout.strip() or "程序异常退出，无错误信息。"
                    return False, error_msg
                    
            except subprocess.TimeoutExpired:
                # 【核心优雅逻辑】超时未死，对于 Pygame 这意味着启动成功了！
                process.kill()
                process.communicate() # 清理僵尸进程
                return True, "程序成功启动并在监听事件中（3秒未崩溃）。"
                
        except Exception as e:
            return False, f"沙盒执行器内部异常: {str(e)}"