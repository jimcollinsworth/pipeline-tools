from typing import Optional, List, Dict, Any, Tuple
from src.core.config import Settings, get_settings
from src.core.ollama_client import OllamaClient
from src.core.gemini_client import GeminiClient


class LLMService:
    """Unified LLM router supporting Ollama, Gemini, and future cloud providers."""

    PROVIDERS = ["Ollama", "Gemini"]

    @classmethod
    def get_provider_client(cls, provider: str, settings: Optional[Settings] = None) -> Any:
        curr_settings = settings or get_settings()
        prov = (provider or "Ollama").strip().lower()

        if prov == "gemini":
            return GeminiClient(api_key=curr_settings.gemini_api_key)
        else:
            return OllamaClient(host=curr_settings.ollama_host)

    @classmethod
    def check_connection(cls, provider: str, settings: Optional[Settings] = None) -> Tuple[bool, str]:
        """Test connectivity for a given provider."""
        client = cls.get_provider_client(provider, settings)
        return client.check_connection()

    @classmethod
    def list_models_for_provider(cls, provider: str, settings: Optional[Settings] = None) -> List[str]:
        """Return available model names for the selected provider. Returns empty list if provider is unreachable."""
        curr_settings = settings or get_settings()
        prov = (provider or "Ollama").strip().lower()

        if prov == "gemini":
            client = GeminiClient(api_key=curr_settings.gemini_api_key)
            return [m["name"] for m in client.list_models()]
        else:
            client = OllamaClient(host=curr_settings.ollama_host)
            models = client.list_models()
            if models:
                return [m["name"] for m in models]
            return []

    @classmethod
    def validate_startup_connections(cls, settings: Optional[Settings] = None) -> Dict[str, Any]:
        """Pre-flight check of configured LLM providers at startup to ensure invalid providers/models are not displayed."""
        curr_settings = settings or get_settings()
        results: Dict[str, Any] = {}

        # 1. Check Ollama
        ollama_client = OllamaClient(host=curr_settings.ollama_host)
        ollama_ok, ollama_msg = ollama_client.check_connection()
        ollama_models = []
        if ollama_ok:
            raw_models = ollama_client.list_models()
            ollama_models = [m["name"] for m in raw_models]
        results["ollama"] = {
            "connected": ollama_ok,
            "message": ollama_msg,
            "models": ollama_models
        }

        # 2. Check Gemini
        gemini_client = GeminiClient(api_key=curr_settings.gemini_api_key)
        gemini_ok, gemini_msg = gemini_client.check_connection()
        gemini_models = [m["name"] for m in gemini_client.list_models()] if gemini_ok or not curr_settings.gemini_api_key else []
        results["gemini"] = {
            "connected": gemini_ok,
            "message": gemini_msg,
            "models": gemini_models
        }

        return results

    @classmethod
    def generate(cls, provider: str, model: str, prompt: str, system: Optional[str] = None,
                 media_path: Optional[str] = None, json_mode: bool = False,
                 settings: Optional[Settings] = None) -> str:
        """Unified generate endpoint across providers with multimodal and json_mode support."""
        curr_settings = settings or get_settings()
        prov = (provider or "Ollama").strip().lower()

        if prov == "gemini":
            client = GeminiClient(api_key=curr_settings.gemini_api_key)
            return client.generate(
                model=model,
                prompt=prompt,
                system=system,
                media_path=media_path,
                json_mode=json_mode
            )
        else:
            client = OllamaClient(host=curr_settings.ollama_host)
            return client.generate(
                model=model,
                prompt=prompt,
                system=system or "",
                media_path=media_path,
                json_mode=json_mode
            )

