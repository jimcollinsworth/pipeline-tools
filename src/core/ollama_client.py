import urllib.request
import urllib.error
import json
from typing import List, Dict, Any, Tuple, Optional

class OllamaClient:
    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host.rstrip("/")

    def check_connection(self) -> Tuple[bool, str]:
        """Test if Ollama server is running and accessible."""
        try:
            req = urllib.request.Request(f"{self.host}/api/version", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return True, f"Connected to Ollama (Version {data.get('version', 'unknown')})"
                return False, f"Server responded with HTTP {resp.status}"
        except urllib.error.URLError as e:
            return False, f"Cannot connect to Ollama at {self.host}: {e.reason}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def list_models(self) -> List[Dict[str, Any]]:
        """List locally available models with sizes and parameter counts."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = data.get("models", [])
                    res = []
                    for m in models:
                        size_gb = round(m.get("size", 0) / (1024 * 1024 * 1024), 2)
                        details = m.get("details", {})
                        res.append({
                            "name": m.get("name"),
                            "size": f"{size_gb} GB",
                            "family": details.get("family", "-"),
                            "parameter_size": details.get("parameter_size", "-"),
                            "quantization": details.get("quantization_level", "-"),
                            "modified_at": m.get("modified_at", "")[:19].replace("T", " ")
                        })
                    return res
                return []
        except Exception:
            return []

    def generate(self, model: str, prompt: str, system: str = "", media_path: Optional[str] = None, json_mode: bool = False) -> str:
        """Single prompt generation against Ollama with optional image and json format."""
        import base64
        import os
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        if media_path and os.path.exists(media_path):
            ext = os.path.splitext(media_path)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                try:
                    with open(media_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    payload["images"] = [b64]
                except Exception:
                    pass

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
