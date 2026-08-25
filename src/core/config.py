import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

CONFIG_FILE = Path("config.json")

class Settings(BaseModel):
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama Server URL")
    default_ollama_model: str = Field(default="llama3.2", description="Default Ollama model for prompts")
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API Key (for future use)")
    pixeltable_dir: str = Field(default=".pixeltable_data", description="Directory for Pixeltable storage")
    default_ingest_dir: str = Field(default="", description="Default source directory for ingestion")
    export_dir: str = Field(default="exports", description="Default export output directory")

def load_settings() -> Settings:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Settings(**data)
        except Exception:
            pass
    return Settings()

def save_settings(settings: Settings) -> Settings:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, indent=2)
    return settings

def get_settings() -> Settings:
    return load_settings()
