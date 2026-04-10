import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

class ProjectManifest:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.manifest_file = project_path / ".forge_manifest.json"
        self.data = self._load()

    def _load(self) -> Dict:
        if self.manifest_file.exists():
            with open(self.manifest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "project": str(self.project_path),
            "created": datetime.now().isoformat(),
            "files": {}
        }

    def save(self):
        with open(self.manifest_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def update_file(self, filename: str, content: str, description: str = ""):
        self.data["files"][filename] = {
            "description": description or self._extract_first_comment(content),
            "size": len(content),
            "updated": datetime.now().isoformat()
        }
        self.save()

    def _extract_first_comment(self, content: str) -> str:
        lines = content.splitlines()
        for line in lines[:3]:
            line = line.strip()
            if line.startswith('#') or line.startswith('//'):
                return line.lstrip('#/ ').strip()[:80]
        return ""

    def get_progress_summary(self) -> str:
        if not self.data["files"]:
            return "项目当前无任何文件。"

        lines = ["## 已有文件及接口"]
        for name, info in self.data["files"].items():
            desc = info.get("description", "")
            lines.append(f"- `{name}`: {desc}")
        if "requirements.txt" not in self.data["files"]:
            lines.append("\n⚠️ 尚未生成 requirements.txt")
        return "\n".join(lines)