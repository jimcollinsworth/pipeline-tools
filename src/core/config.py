import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field

CONFIG_FILE = Path("config.json")

def sanitize_identifier(name: str) -> Tuple[bool, str, str]:
    """
    Validate and sanitize Pixeltable domain/table identifiers.
    Rules:
    - Must start with a letter or underscore (no leading digits).
    - Can contain letters, digits, underscores (dashes are replaced with underscores).
    - Cannot be empty.
    Returns: (is_valid, sanitized_name, message)
    """
    raw = name.strip()
    if not raw:
        return False, "", "Name cannot be empty."

    # Replace dashes and spaces with underscores
    sanitized = re.sub(r'[\s\-]+', '_', raw)
    # Remove any character that is not alphanumeric or underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', sanitized)

    if not sanitized:
        return False, "", f"Invalid identifier '{raw}': contains no valid alphanumeric characters."

    # Ensure starts with a letter or underscore
    if not (sanitized[0].isalpha() or sanitized[0] == '_'):
        sanitized = f"t_{sanitized}"
        return True, sanitized, f"Identifier '{raw}' started with a digit or special char; adjusted to valid format: '{sanitized}'"

    if sanitized != raw:
        return True, sanitized, f"Identifier '{raw}' adjusted to valid SQL/Pixeltable format: '{sanitized}'"

    return True, sanitized, ""

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant extracting entities, summaries, and key metadata from documents."

class Settings(BaseModel):
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama Server URL")
    default_ollama_model: str = Field(default="llama3.2", description="Default Ollama model for prompts")
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API Key")
    default_gemini_model: str = Field(default="gemini-3.6-flash", description="Default Gemini model")
    default_provider: str = Field(default="Ollama", description="Default LLM Provider (Ollama or Gemini)")
    pixeltable_dir: str = Field(default=".pixeltable_data", description="Directory for Pixeltable storage")
    default_ingest_dir: str = Field(default="", description="Default source directory for ingestion")
    export_dir: str = Field(default="exports", description="Default export output directory")
    
    # Persistent UI States
    last_provider: str = Field(default="Ollama", description="Last selected LLM provider")
    last_model: str = Field(default="llama3.2", description="Last selected LLM model")
    last_domain: str = Field(default="default", description="Last used Pixeltable domain")
    last_table: str = Field(default="raw_assets", description="Last used Pixeltable table name")
    last_system_prompt: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        description="Last used system prompt"
    )
    last_user_prompt: str = Field(
        default="Analyze the following document:\nFile: {file_name}\n\nContent:\n{content}\n\nProvide a 2-sentence summary and extract top 3 key entities as JSON.",
        description="Last used user prompt template"
    )
    domain_system_prompts: Dict[str, str] = Field(
        default_factory=lambda: {"default": DEFAULT_SYSTEM_PROMPT},
        description="System prompts configured per domain"
    )

def load_env_file():
    """Lightweight zero-dependency .env file reader."""
    env_file = Path(".env")
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

def load_settings() -> Settings:
    settings = Settings()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                settings = Settings(**data)
        except Exception:
            pass
            
    # Guarantee per-domain system prompts dictionary initialization
    if not settings.domain_system_prompts:
        settings.domain_system_prompts = {"default": settings.last_system_prompt or DEFAULT_SYSTEM_PROMPT}
    elif "default" not in settings.domain_system_prompts:
        settings.domain_system_prompts["default"] = settings.last_system_prompt or DEFAULT_SYSTEM_PROMPT

    # Environment variable fallbacks
    if not settings.gemini_api_key and os.environ.get("GEMINI_API_KEY"):
        settings.gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if os.environ.get("OLLAMA_HOST"):
        settings.ollama_host = os.environ.get("OLLAMA_HOST")

    # In cloud container environments (Hugging Face Spaces), default to Gemini
    if os.environ.get("SPACE_ID"):
        settings.default_provider = "Gemini"
        if settings.last_provider == "Ollama":
            settings.last_provider = "Gemini"
            settings.last_model = settings.default_gemini_model or "gemini-3.6-flash"
        
    return settings

def save_settings(settings: Settings) -> Settings:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, indent=2)
    return settings

def get_domain_system_prompt(domain: Optional[str] = None) -> str:
    """Retrieve the configured system prompt for a specific domain with default fallback."""
    s = load_settings()
    dom = domain.strip() if domain and domain.strip() else "default"
    if s.domain_system_prompts and dom in s.domain_system_prompts and s.domain_system_prompts[dom].strip():
        return s.domain_system_prompts[dom]
    if s.domain_system_prompts and "default" in s.domain_system_prompts and s.domain_system_prompts["default"].strip():
        return s.domain_system_prompts["default"]
    return s.last_system_prompt or DEFAULT_SYSTEM_PROMPT

def set_domain_system_prompt(domain: Optional[str], prompt: str) -> Settings:
    """Update and persist the system prompt for a specific domain."""
    s = load_settings()
    dom = domain.strip() if domain and domain.strip() else "default"
    if s.domain_system_prompts is None:
        s.domain_system_prompts = {}
    cleaned_prompt = prompt.strip()
    s.domain_system_prompts[dom] = cleaned_prompt
    s.last_system_prompt = cleaned_prompt
    save_settings(s)
    return s

def update_last_entry(**kwargs) -> Settings:
    s = load_settings()
    updated = False
    for k, v in kwargs.items():
        if hasattr(s, k) and v is not None:
            setattr(s, k, v)
            updated = True
    if updated:
        save_settings(s)
    return s

def get_settings() -> Settings:
    return load_settings()

