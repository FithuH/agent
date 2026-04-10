#!/usr/bin/env python3
"""
forge-project - AI 驱动的项目脚手架生成器
用法: python forge.py "做一个12306抢票脚本"
"""
import argparse
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径，以便导入模块
sys.path.insert(0, str(Path(__file__).parent))

from core.orchestrator import Orchestrator
from utils.logger import setup_logger

def main():
    parser = argparse.ArgumentParser(
        description="AI 驱动的项目生成器 - 用自然语言描述需求，自动生成完整项目"
    )
    parser.add_argument(
        "requirement",
        type=str,
        help="项目需求描述，例如 '做一个12306抢票脚本'"
    )
    parser.add_argument(
        "--name",
        type=str,
        help="项目名称（可选，默认从需求生成）"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="./output",
        help="输出目录（默认: ./output）"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config.yaml",
        help="配置文件路径（默认: config.yaml）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志"
    )
    
    args = parser.parse_args()
    
    # 配置日志级别
    log_level = "DEBUG" if args.verbose else "INFO"
    logger = setup_logger("forge", level=log_level)
    
    try:
        orchestrator = Orchestrator(config_path=args.config)
        project_path = orchestrator.run(
            requirement=args.requirement,
            project_name=args.name,
            output_dir=args.output
        )
        print(f"\n✅ 项目生成成功！位置: {project_path}")
    except Exception as e:
        logger.error(f"项目生成失败: {e}", exc_info=args.verbose)
        sys.exit(1)

if __name__ == "__main__":
    main()