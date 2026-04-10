import logging
import sys
from pathlib import Path
from typing import Optional
import colorlog

def setup_logger(
    name: str = "forge",
    level: str = "INFO",
    log_file: Optional[Path] = None
) -> logging.Logger:
    """配置彩色日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 控制台处理器 - 彩色输出
    console_handler = colorlog.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger