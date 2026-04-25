#!/usr/bin/env python3
"""
forge-project - AI 驱动的项目脚手架生成器
用法: 
  1. 直接输入需求: python forge.py "做一个简单的待办事项命令行工具"
  2. 使用文件输入: python forge.py prompt.txt
"""
import argparse
import sys
import os
import traceback
from pathlib import Path

# =====================================================================
# [网络层工程排坑] 强制路由分流 (Split Routing)
# 阻断 VPN 环境变量对本地 Ollama 以及国内直连 API (DeepSeek) 的污染
# 必须在导入 core 模块（及底层的 httpx/requests）之前执行
# =====================================================================
BYPASS_DOMAINS = "localhost,127.0.0.1,0.0.0.0,api.deepseek.com"
os.environ["NO_PROXY"] = BYPASS_DOMAINS
os.environ["no_proxy"] = BYPASS_DOMAINS

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
        help="项目需求描述（例如 '做一个待办工具'），或者包含详细需求的 .txt 文件路径"
    )
    parser.add_argument(
        "--name",
        type=str,
        help="项目名称（可选，默认从需求生成或默认为 generated_project）"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None, 
        help="输出目录（可选，覆盖 config.yaml 中的默认设置）"
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

    # ==========================================
    # [核心修改] 支持文件或直接文本输入
    # ==========================================
    req_input = args.requirement
    req_path = Path(req_input)
    
    # 判断输入是否为一个存在的文件
    if req_path.is_file():
        logger.info(f"📄 检测到输入为文件: {req_path.resolve()}，正在读取内容...")
        try:
            with open(req_path, 'r', encoding='utf-8') as f:
                actual_requirement = f.read().strip()
                if not actual_requirement:
                    logger.error("需求文件为空，请输入有效的需求。")
                    sys.exit(1)
                logger.info("✅ 成功加载外部需求文档！")
        except Exception as e:
            logger.error(f"❌ 读取需求文件失败: {e}")
            sys.exit(1)
    else:
        # 如果不是文件，则直接作为字符串处理
        actual_requirement = req_input
        logger.info("💬 接收到直接文本需求输入。")

    try:
        logger.info("Initializing Forge Orchestrator (Bypassing VPN for local & DeepSeek)...")
        orchestrator = Orchestrator(config_path=args.config)
        
        # 将解析后的实际文本传入
        output_path = orchestrator.run(
            requirement=actual_requirement, 
            name=args.name
        )
        logger.info(f"🎉 项目已成功生成至: {output_path}")
        
    except Exception as e:
        logger.error(f"❌ 运行失败: {e}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()