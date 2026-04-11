"""Configuration loader/saver for MP-Camera."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Optional dependency: jsonschema
try:
    import jsonschema  # type: ignore

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

# Constants
SCHEMA_PATH = Path(__file__).resolve().parent / "config_schema.json"
DEFAULT_USER_CONFIG = Path.home() / ".mpcamera" / "config.json"

# Global singleton cache
_GLOBAL_SETTINGS: Settings | None = None


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base (non-destructive)."""
    out = base.copy()
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def _extract_defaults(schema: dict[str, Any]) -> Any:
    """Recursively extract default values from the JSON schema."""
    if "default" in schema:
        return schema["default"]

    if schema.get("type") == "object":
        defaults = {}
        for k, v in schema.get("properties", {}).items():
            val = _extract_defaults(v)
            if val is not None:
                defaults[k] = val
        return defaults if defaults else None

    return None


class Settings(dict):
    """Dict-like settings object allowing attribute access (s.key)."""

    def __getattr__(self, key: str) -> Any:
        try:
            val = self[key]
        except KeyError as e:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{key}'"
            ) from e

        # Lazy conversion of nested dicts to Settings
        if isinstance(val, dict) and not isinstance(val, Settings):
            val = Settings(val)
            self[key] = val
        return val

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def save(self, path: str | Path | None = None) -> None:
        """Save current settings to JSON."""
        p = Path(path) if path else DEFAULT_USER_CONFIG
        p.parent.mkdir(parents=True, exist_ok=True)

        with p.open("w", encoding="utf-8") as fh:
            # Settings inherits dict, so json.dump handles it nativey
            json.dump(self, fh, indent=2, ensure_ascii=False)

    @classmethod
    def load(
        cls, path: str | Path | None = None, schema_path: Path | None = None
    ) -> Settings:
        """Load settings, merging schema defaults with user config."""
        # 1. Load Schema & Defaults
        s_path = schema_path or SCHEMA_PATH
        try:
            schema = json.loads(s_path.read_text(encoding="utf-8"))
            defaults = _extract_defaults(schema) or {}
        except Exception as e:
            raise RuntimeError(f"Failed to load schema {s_path}: {e}")

        # 2. Load User Config
        u_path = Path(path) if path else DEFAULT_USER_CONFIG
        user_conf = {}
        if u_path.exists():
            try:
                user_conf = json.loads(u_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print(
                    f"Warning: Invalid JSON in {u_path}, using defaults.",
                    file=sys.stderr,
                )

        # 3. Merge
        merged = _deep_update(defaults, user_conf)

        # 4. Validate (if available)
        if _HAS_JSONSCHEMA:
            try:
                jsonschema.validate(instance=merged, schema=schema)
            except jsonschema.ValidationError as e:
                print(f"Config validation warning: {e.message}", file=sys.stderr)

        return cls(merged)


def get_settings(path: str | Path | None = None) -> Settings:
    """Get or create the global cached Settings instance."""
    global _GLOBAL_SETTINGS
    if _GLOBAL_SETTINGS is None:
        logger.debug(f"Loading settings from {path or DEFAULT_USER_CONFIG}")
        _GLOBAL_SETTINGS = Settings.load(path)
        logger.info("Settings loaded successfully")
    return _GLOBAL_SETTINGS


def set_settings(settings: Settings) -> None:
    """Override the global settings instance."""
    global _GLOBAL_SETTINGS
    _GLOBAL_SETTINGS = settings


def sync_env_to_config() -> None:
    """Read API URLs and keys from .env file and sync to config.json if they're set."""
    import os
    from dotenv import load_dotenv

    # Load .env file
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        logger.debug(".env file not found; skipping env sync")
        return

    try:
        logger.debug(f"Loading .env from {env_path}")
        load_dotenv(env_path)
    except Exception as e:
        logger.warning(f"Failed to load .env: {e}")
        return

    # Get settings
    try:
        cfg = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings for env sync: {e}")
        return

    # Sync Roboflow API URL
    rf_url = os.getenv("ROBOFLOW_API_URL")
    if rf_url and rf_url.strip():
        if not cfg.get("services", {}).get("roboflow", {}).get("api_url") or \
           cfg["services"]["roboflow"]["api_url"] == "http://localhost:9001":
            # Only override if empty or still default
            cfg["services"]["roboflow"]["api_url"] = rf_url.strip()

    # Sync Roboflow API Key
    rf_key = os.getenv("ROBOFLOW_API_KEY")
    if rf_key and rf_key.strip():
        if not cfg.get("services", {}).get("roboflow", {}).get("api_key"):
            # Only override if empty
            cfg["services"]["roboflow"]["api_key"] = rf_key.strip()

    # Sync Directus API URL
    du_url = os.getenv("DIRECTUS_API_URL")
    if du_url and du_url.strip():
        if not cfg.get("services", {}).get("directus", {}).get("api_url"):
            # Only override if empty
            cfg["services"]["directus"]["api_url"] = du_url.strip()

    # Sync Directus Bearer Token
    du_token = os.getenv("DIRECTUS_BEARER_TOKEN")
    if du_token and du_token.strip():
        if not cfg.get("services", {}).get("directus", {}).get("bearer_token"):
            # Only override if empty
            cfg["services"]["directus"]["bearer_token"] = du_token.strip()

    # Save updated config
    try:
        cfg.save()
    except Exception:
        pass
