import os
from typing import Optional, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv
from utils.logger import setup_logger
from utils.retry import retry

load_dotenv()
logger = setup_logger(__name__)

class RemoteAPIClient:
    """封装 DeepSeek API 调用"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        system_prompt_path: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment or arguments")
        
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # 加载系统提示词
        from pathlib import Path
        if system_prompt_path is None:
            system_prompt_path = Path(__file__).parent.parent / "templates" / "prompts" / "coder_system.txt"
        self.system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")
    
    @retry(exceptions=(Exception,), max_attempts=3, delay=2.0)
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        调用远程 API 生成内容，支持重试
        """
        logger.info(f"Calling remote API with prompt length: {len(prompt)}")
        
        messages = [
            {"role": "system", "content": system_prompt or self.system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False
            )
            content = response.choices[0].message.content
            logger.debug(f"API response length: {len(content)}")
            return content
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise