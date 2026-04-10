import json
from typing import Any, Dict, List

def validate_json_response(text: str, expected_keys: List[str]) -> Dict[str, Any]:
    """从文本中提取并验证 JSON"""
    # 尝试提取 JSON 代码块
    import re
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        # 尝试查找第一个 { 到最后一个 } 的内容
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]
    
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}")
    
    # 验证必要字段
    missing = [key for key in expected_keys if key not in data]
    if missing:
        raise ValueError(f"Missing expected keys in JSON: {missing}")
    
    return data