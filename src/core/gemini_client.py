import os
from typing import Optional, List, Tuple, Dict, Any

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class GeminiClient:
    """Client for Google Gemini API via modern google-genai SDK."""

    SUPPORTED_MODELS = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite",
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def get_client(self, api_key: Optional[str] = None) -> Any:
        key = api_key or self.api_key
        if not key:
            raise ValueError("Gemini API key is required. Please set your API key in the Settings tab or GEMINI_API_KEY environment variable.")
        if not GEMINI_AVAILABLE:
            raise RuntimeError("google-genai package is not installed. Run `uv pip install google-genai`.")
        return genai.Client(api_key=key)

    def check_connection(self, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """Test API key validity with a lightweight call."""
        key = api_key or self.api_key
        if not key or not key.strip():
            return False, "⚠️ Gemini API key is missing. Please enter your API key."
        
        if not GEMINI_AVAILABLE:
            return False, "❌ `google-genai` package is not installed."

        try:
            client = genai.Client(api_key=key.strip())
            # Test with a minimal generation
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=5)
            )
            return True, "✅ Successfully connected to Google Gemini API!"
        except Exception as e:
            err_msg = str(e)
            if "API_KEY_INVALID" in err_msg or "400" in err_msg or "API key not valid" in err_msg:
                return False, "❌ Invalid Gemini API key. Please check your credentials."
            elif "PERMISSION_DENIED" in err_msg:
                return False, f"❌ Permission denied: {err_msg}"
            return False, f"❌ Connection failed: {err_msg}"

    def list_models(self) -> List[Dict[str, str]]:
        """Return list of supported Gemini models with descriptions."""
        model_info = [
            {"name": "gemini-3.6-flash", "description": "1M tokens — Fast, balanced, state-of-the-art general model (Recommended)"},
            {"name": "gemini-3.5-flash-lite", "description": "1M tokens — Lowest latency & cost for high-throughput execution"},
            {"name": "gemini-3.1-pro-preview", "description": "1M tokens — Advanced reasoning, complex analysis, and coding"},
            {"name": "gemini-3.1-flash-lite", "description": "Cost-efficient, ultra-fast performance for lightweight tasks"},
            {"name": "gemma-4-31b-it", "description": "Gemma 4 Dense 31B instruction-tuned open weights"},
            {"name": "gemma-4-26b-a4b-it", "description": "Gemma 4 MoE 26B total / 4B active parameters"},
        ]
        return model_info

    def generate(self, model: str, prompt: str, system: Optional[str] = None, api_key: Optional[str] = None) -> str:
        """Generate text using Gemini models."""
        client = self.get_client(api_key)
        target_model = model or "gemini-3.6-flash"

        config = None
        if system and system.strip():
            config = types.GenerateContentConfig(system_instruction=system.strip())

        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config
            )
            if response.text:
                return response.text.strip()
            return "[Empty response from Gemini]"
        except Exception as e:
            raise RuntimeError(f"Gemini generation failed: {type(e).__name__}: {str(e)}")
