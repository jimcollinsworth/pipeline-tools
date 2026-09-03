import os
import logging
from typing import Optional, List, Tuple, Dict, Any

# Suppress SDK-level informational warnings (e.g. AFC recommendations)
logging.getLogger("google_genai").setLevel(logging.ERROR)

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
        self.last_telemetry: Dict[str, Any] = {}

    def get_client(self, api_key: Optional[str] = None) -> Any:
        key = self.api_key if api_key is None else api_key
        if not key:
            raise ValueError("Gemini API key is required. Please set your API key in the Settings tab or GEMINI_API_KEY environment variable.")
        if not GEMINI_AVAILABLE:
            raise RuntimeError("google-genai package is not installed. Run `uv pip install google-genai`.")
        return genai.Client(api_key=key)

    def check_connection(self, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """Test API key validity with a lightweight call."""
        key = self.api_key if api_key is None else api_key
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

    def list_models(self, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Dynamically query available Gemini models from Google API with rich metadata."""
        key = self.api_key if api_key is None else api_key
        if key and key.strip() and GEMINI_AVAILABLE:
            try:
                client = genai.Client(api_key=key.strip())
                live_models = []
                for m in client.models.list():
                    raw_name = getattr(m, "name", "")
                    clean_name = raw_name.replace("models/", "").strip() if raw_name else ""
                    if not clean_name:
                        continue

                    # Filter for generative chat/vision models (exclude embeddings, aqa, and legacy bison)
                    name_lower = clean_name.lower()
                    if "embedding" in name_lower or "aqa" in name_lower or "bison" in name_lower:
                        continue

                    supported = getattr(m, "supported_actions", []) or getattr(m, "supported_generation_methods", [])
                    is_gen = True
                    if supported:
                        is_gen = any("generatecontent" in str(s).lower() for s in supported)

                    if is_gen and ("gemini" in name_lower or "gemma" in name_lower):
                        display = getattr(m, "display_name", "") or clean_name
                        input_limit = getattr(m, "input_token_limit", None)
                        output_limit = getattr(m, "output_token_limit", None)
                        
                        input_str = f"{input_limit:,} tokens" if input_limit else "1,048,576 tokens"
                        output_str = f"{output_limit:,} tokens" if output_limit else "8,192 tokens"
                        
                        # Inferred modalities
                        modalities = "Text, Vision, PDF, Audio, Video" if "flash" in name_lower or "pro" in name_lower else "Text, Code"
                        
                        # Inferred cost tier
                        if "gemma" in name_lower:
                            cost_tier = "Open Weights (Free)"
                        elif "flash-lite" in name_lower:
                            cost_tier = "Ultra Low ($0.038 / 1M tokens)"
                        elif "flash" in name_lower:
                            cost_tier = "Standard ($0.075 / 1M tokens)"
                        elif "pro" in name_lower:
                            cost_tier = "Advanced ($1.25 / 1M tokens)"
                        else:
                            cost_tier = "Pay-as-you-go"

                        desc = getattr(m, "description", "") or display
                        
                        live_models.append({
                            "name": clean_name,
                            "display_name": display,
                            "modalities": modalities,
                            "input_window": input_str,
                            "output_limit": output_str,
                            "cost_tier": cost_tier,
                            "description": desc.strip()[:140]
                        })

                if live_models:
                    live_models.sort(key=lambda x: (x["name"].startswith("gemini"), x["name"]), reverse=True)
                    return live_models
            except Exception:
                pass

        # Fallback baseline list if offline or API key is not yet configured
        return [
            {
                "name": "gemini-3.7-flash",
                "display_name": "Gemini 3.7 Flash",
                "modalities": "Text, Vision, PDF, Audio, Video",
                "input_window": "1,048,576 tokens",
                "output_limit": "8,192 tokens",
                "cost_tier": "Standard ($0.075 / 1M tokens)",
                "description": "Next-gen hybrid reasoning & coding speed"
            },
            {
                "name": "gemini-3.6-flash",
                "display_name": "Gemini 3.6 Flash",
                "modalities": "Text, Vision, PDF, Audio, Video",
                "input_window": "1,048,576 tokens",
                "output_limit": "8,192 tokens",
                "cost_tier": "Standard ($0.075 / 1M tokens)",
                "description": "Fast, balanced, state-of-the-art general model (Recommended)"
            },
            {
                "name": "gemini-3.5-flash-lite",
                "display_name": "Gemini 3.5 Flash-Lite",
                "modalities": "Text, Vision, PDF",
                "input_window": "1,048,576 tokens",
                "output_limit": "8,192 tokens",
                "cost_tier": "Ultra Low ($0.038 / 1M tokens)",
                "description": "Lowest latency & cost for high-throughput batch execution"
            },
            {
                "name": "gemini-3.1-pro-preview",
                "display_name": "Gemini 3.1 Pro",
                "modalities": "Text, Vision, PDF, Audio, Video",
                "input_window": "2,097,152 tokens",
                "output_limit": "8,192 tokens",
                "cost_tier": "Advanced ($1.25 / 1M tokens)",
                "description": "Advanced reasoning, complex analysis, and coding"
            },
            {
                "name": "gemini-3.1-flash-lite",
                "display_name": "Gemini 3.1 Flash-Lite",
                "modalities": "Text, Vision, PDF",
                "input_window": "1,048,576 tokens",
                "output_limit": "8,192 tokens",
                "cost_tier": "Ultra Low ($0.038 / 1M tokens)",
                "description": "Cost-efficient, ultra-fast performance for lightweight tasks"
            },
            {
                "name": "gemma-4-31b-it",
                "display_name": "Gemma 4 31B IT",
                "modalities": "Text, Code",
                "input_window": "131,072 tokens",
                "output_limit": "8,192 tokens",
                "cost_tier": "Open Weights (Free)",
                "description": "Gemma 4 Dense 31B instruction-tuned open weights"
            },
            {
                "name": "gemma-4-26b-a4b-it",
                "display_name": "Gemma 4 26B A4B",
                "modalities": "Text, Code",
                "input_window": "131,072 tokens",
                "output_limit": "8,192 tokens",
                "cost_tier": "Open Weights (Free)",
                "description": "Gemma 4 MoE 26B total / 4B active parameters"
            },
        ]



    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        api_key: Optional[str] = None,
        media_path: Optional[str] = None,
        json_mode: bool = False
    ) -> str:
        """Generate text or structured JSON using Gemini models with optional multimodal media."""
        client = self.get_client(api_key)
        target_model = model or "gemini-3.6-flash"

        config_kwargs: Dict[str, Any] = {}
        if system and system.strip():
            config_kwargs["system_instruction"] = system.strip()
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        contents: Any = prompt
        if media_path and os.path.exists(media_path):
            import mimetypes
            mime, _ = mimetypes.guess_type(media_path)
            if not mime:
                ext = os.path.splitext(media_path)[1].lower()
                if ext in [".jpg", ".jpeg"]:
                    mime = "image/jpeg"
                elif ext == ".png":
                    mime = "image/png"
                elif ext == ".webp":
                    mime = "image/webp"
                elif ext == ".pdf":
                    mime = "application/pdf"
            
            if mime and (mime.startswith("image/") or mime == "application/pdf"):
                try:
                    with open(media_path, "rb") as f:
                        media_bytes = f.read()
                    contents = [
                        types.Part.from_bytes(data=media_bytes, mime_type=mime),
                        prompt
                    ]
                except Exception:
                    contents = prompt

        import time
        start_t = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=contents,
                config=config
            )
            elapsed_sec = round(time.perf_counter() - start_t, 2)
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
            eval_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
            tps = round(eval_tokens / elapsed_sec, 1) if elapsed_sec > 0 and eval_tokens > 0 else 0.0

            self.last_telemetry = {
                "provider": "Gemini",
                "model": target_model,
                "total_sec": elapsed_sec,
                "eval_sec": elapsed_sec,
                "eval_tokens": eval_tokens,
                "eval_tps": tps,
                "prompt_tokens": prompt_tokens,
                "summary": f"⏱️ {elapsed_sec}s ({tps} tok/s) | Ingest: {prompt_tokens} tok | Generated: {eval_tokens} tok | Model: {target_model}"
            }

            if response.text:
                return response.text.strip()
            return "{}" if json_mode else "[Empty response from Gemini]"
        except Exception as e:
            raise RuntimeError(f"Gemini generation failed: {type(e).__name__}: {str(e)}")

