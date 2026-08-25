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

class Settings(BaseModel):
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama Server URL")
    default_ollama_model: str = Field(default="llama3.2", description="Default Ollama model for prompts")
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API Key (for future use)")
    pixeltable_dir: str = Field(default=".pixeltable_data", description="Directory for Pixeltable storage")
    default_ingest_dir: str = Field(default="", description="Default source directory for ingestion")
    export_dir: str = Field(default="exports", description="Default export output directory")
    
    # Persistent UI States
    last_domain: str = Field(default="default", description="Last used Pixeltable domain")
    last_table: str = Field(default="raw_assets", description="Last used Pixeltable table name")
    last_system_prompt: str = Field(
        default="You are a helpful AI assistant extracting entities, summaries, and key metadata from documents.",
        description="Last used system prompt"
    )
    last_user_prompt: str = Field(
        default="Analyze the following document:\nFile: {file_name}\n\nContent:\n{content}\n\nProvide a 2-sentence summary and extract top 3 key entities as JSON.",
        description="Last used user prompt template"
    )

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

