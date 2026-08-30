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
        """Return available model names for the selected provider."""
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
            return [curr_settings.default_ollama_model, "llama3.2", "mistral", "phi3"]

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

