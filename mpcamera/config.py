"""Configuration loader/saver for MP-Camera.

Features:
- Loads defaults from `config_schema.json` shipped in the package.
- Validates user config against the schema using `jsonschema` when available.
- Merges user config over defaults and exposes a `Settings` object (dict-like and attribute access).
- Persists user config to a JSON file (default: `%USERPROFILE%/.mpcamera/config.json` on Windows or `$HOME/.mpcamera/config.json`).

Usage:
    from mpcamera.config import Settings
    s = Settings.load()  # loads default + user's file if present
    print(s.inference.default_confidence)
    s.inference.default_confidence = 0.45
    s.save()

The module avoids hard failures when `jsonschema` is not installed; it will still load and save config but skip strict validation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

# Try to import jsonschema for validation; fall back gracefully
try:
    import jsonschema  # type: ignore

    _HAS_JSONSCHEMA = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_JSONSCHEMA = False


_SCHEMA_PATH = Path(__file__).resolve().parent / "config_schema.json"


def _load_schema() -> Dict[str, Any]:
    try:
        with _SCHEMA_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:  # pragma: no cover - simple file read
        raise RuntimeError(f"Failed to load config schema: {_SCHEMA_PATH}: {e}")


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively update `base` with values from `override` (non-destructive).

    Returns a new dict (does not mutate inputs).
    """
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def _extract_defaults_from_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Walk the schema and produce a dict of defaults for top-level properties only.

    This is intentionally conservative: it uses the `default` keys present in the
    schema for nested objects when available. It's good enough to seed settings with
    sensible values; the application can persist user changes afterwards.
    """

    def pick_defaults(node: Dict[str, Any]) -> Any:
        t = node.get("type")
        if "default" in node:
            return node["default"]
        if t == "object":
            props = node.get("properties", {})
            return {
                k: pick_defaults(v)
                for k, v in props.items()
                if "default" in v or v.get("type") == "object"
            }
        # no default available
        return None

    root = {}
    props = schema.get("properties", {})
    for name, prop in props.items():
        val = pick_defaults(prop)
        if val is not None:
            root[name] = val
    return root


class Settings(dict):
    """Dict-like settings object allowing attribute access.

    Example: `s.inference['default_confidence']` or `s.inference.default_confidence`.
    """

    def __getattr__(self, item):
        try:
            v = self[item]
        except KeyError as e:
            raise AttributeError(item) from e
        if isinstance(v, dict) and not isinstance(v, Settings):
            v = Settings(v)
            self[item] = v
        return v

    def __setattr__(self, key, value):
        # Allow normal attribute setting for internal names
        if key.startswith("_"):
            super().__setattr__(key, value)
            return
        self[key] = value

    def save(self, path: str | None = None) -> None:
        """Save the user config to `path` or to the default user config location."""
        p = (
            Path(path)
            if path
            else Path(os.path.expanduser("~")) / ".mpcamera" / "config.json"
        )
        p.parent.mkdir(parents=True, exist_ok=True)
        # Convert Settings -> plain dict
        to_write = json.loads(
            json.dumps(
                self, default=lambda o: dict(o) if isinstance(o, Settings) else o
            )
        )
        with p.open("w", encoding="utf-8") as fh:
            json.dump(to_write, fh, indent=2, ensure_ascii=False)

    @staticmethod
    def load(path: str | None = None, schema_path: str | None = None) -> "Settings":
        """Load settings. Merges schema defaults with user file (if present).

        - `path`: optional path to user config JSON. If omitted uses `~/.mpcamera/config.json`.
        - `schema_path`: optional path to a JSON Schema file. Defaults to packaged `config_schema.json`.
        """
        schema = (
            _load_schema()
            if schema_path is None
            else json.loads(Path(schema_path).read_text(encoding="utf-8"))
        )

        defaults = _extract_defaults_from_schema(schema)

        # Read user config if present
        user_path = (
            Path(path)
            if path
            else Path(os.path.expanduser("~")) / ".mpcamera" / "config.json"
        )
        user_conf = {}
        if user_path.exists():
            try:
                user_conf = json.loads(user_path.read_text(encoding="utf-8"))
            except Exception:
                # If file is invalid JSON, ignore and continue with defaults
                user_conf = {}

        merged = _deep_update(defaults, user_conf)

        # Validate if jsonschema available
        if _HAS_JSONSCHEMA:
            try:
                # Use Draft7Validator for compatibility with the schema shipped
                jsonschema.validate(instance=merged, schema=schema)
            except Exception as e:  # pragma: no cover - runtime validation
                # Do not hard-fail; surface as warning in runtime environments
                print(f"Config validation failed: {e}. Using merged values anyway.")

        # Convert nested dicts to Settings objects recursively
        def to_settings(obj: Any) -> Any:
            if isinstance(obj, dict):
                return Settings({k: to_settings(v) for k, v in obj.items()})
            return obj

        return to_settings(merged)


# Convenience functions
def load_settings(path: str | None = None) -> Settings:
    return Settings.load(path)


def save_settings(settings: Settings, path: str | None = None) -> None:
    settings.save(path)
