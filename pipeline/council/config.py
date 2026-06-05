"""Council configuration loader.

Reads `council_config.json` (sibling of this file) and returns the model
assignments and behavior settings for the council. The main project
`config.py` reads the same file to seed its env-var-overridable defaults.

Keeping the model NAMES in a JSON file (not Python) means a non-developer
can change which free model speaks for which role without editing code.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional


_CONFIG_PATH = Path(__file__).parent / "council_config.json"


@lru_cache(maxsize=1)
def load_council_config() -> Dict[str, Any]:
    """Load and cache the council config JSON."""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Council config not found at {_CONFIG_PATH}. "
            "Re-install VisualNote or restore the file."
        )
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def get_member_config(name: str) -> Dict[str, Any]:
    """Return the config dict for a single member, e.g. 'scriptwriter'.

    Raises KeyError if the member is unknown.
    """
    cfg = load_council_config()
    members = cfg.get("members", {})
    if name not in members:
        raise KeyError(
            f"Unknown council member: {name!r}. "
            f"Available: {sorted(members.keys())}"
        )
    return members[name]


def get_fallback_chain() -> list[str]:
    """Return the ordered list of fallback model ids."""
    return list(load_council_config().get("fallback_chain", []))


def get_setting(key: str, default: Any = None) -> Any:
    """Read a top-level setting, e.g. 'enabled', 'max_retries'."""
    return load_council_config().get(key, default)
