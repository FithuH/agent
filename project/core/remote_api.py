import os
import time
from typing import Optional, Dict, Any
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError
from dotenv import load_dotenv
from utils.logger import setup_logger
from utils.retry import retry

load_dotenv()
logger = setup_logger(__name__)


class RemoteAPIClient:
    """封装 DeepSeek API 调用，增强错误处理和重试"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        system_prompt_path: Optional[str] = None,
        max_retries: int = 5,
        retry_delay: float = 2.0
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment or arguments")
        
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 创建客户端，设置超时
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=60.0  # 60秒超时
        )
        
        # 加载系统提示词
        from pathlib import Path
        if system_prompt_path is None:
            system_prompt_path = Path(__file__).parent.parent / "templates" / "prompts" / "coder_system.txt"
        self.system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        调用远程 API 生成内容，支持指数退避重试，专门处理 502/503 等临时性错误
        """
        logger.info(f"Calling remote API with prompt length: {len(prompt)}")
        
        messages = [
            {"role": "system", "content": system_prompt or self.system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        last_exception = None
        for attempt in range(self.max_retries):
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
                
            except (APIConnectionError, APITimeoutError) as e:
                last_exception = e
                logger.warning(f"Connection/timeout error (attempt {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    sleep_time = self.retry_delay * (2 ** attempt)  # 指数退避
                    logger.info(f"Retrying in {sleep_time:.1f} seconds...")
                    time.sleep(sleep_time)
                else:
                    raise RuntimeError(f"Failed to connect to DeepSeek API after {self.max_retries} attempts. Please check your network or try again later.") from e
                    
            except RateLimitError as e:
                last_exception = e
                logger.warning(f"Rate limit exceeded (attempt {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    sleep_time = self.retry_delay * (3 ** attempt)  # 更长的等待
                    logger.info(f"Retrying in {sleep_time:.1f} seconds...")
                    time.sleep(sleep_time)
                else:
                    raise RuntimeError("DeepSeek API rate limit exceeded. Please wait and try again later.") from e
                    
            except APIError as e:
                # 处理 502, 503, 504 等可重试的 HTTP 状态码
                if e.code in [502, 503, 504]:
                    last_exception = e
                    logger.warning(f"API server error {e.code} (attempt {attempt+1}/{self.max_retries}): {e}")
                    if attempt < self.max_retries - 1:
                        sleep_time = self.retry_delay * (2 ** attempt)
                        logger.info(f"Retrying in {sleep_time:.1f} seconds...")
                        time.sleep(sleep_time)
                    else:
                        raise RuntimeError(f"DeepSeek API returned error {e.code} repeatedly. The service may be temporarily unavailable.") from e
                else:
                    # 其他 API 错误不重试，直接抛出
                    logger.error(f"API error: {e}")
                    raise RuntimeError(f"DeepSeek API error: {e}") from e
                    
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise
        
        # 如果所有重试都失败
        raise RuntimeError(f"Failed to generate content: {last_exception}")