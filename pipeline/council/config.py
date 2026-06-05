"""Council configuration loader.

Reads `council_config.json` (sibling of this file) and exposes the model
assignments, behavior settings, phase plan, and per-member system prompts.
The main project `config.py` reads the same file to seed its env-var
overridable defaults.

The orchestrator and CLI tools call into this module to discover which
members exist, which models they use, and how the phases are sequenced —
no Python file needs to know the council's shape ahead of time.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


# Allow overriding the entire config via env var. The default sits next to
# this file so a fresh clone has a working council.
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "council_config.json"


def config_path() -> Path:
    """Return the active council config path. Honors COUNCIL_CONFIG env var."""
    override = os.getenv("COUNCIL_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_CONFIG_PATH


@lru_cache(maxsize=1)
def load_council_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and cache the council config JSON from `path` (or the default)."""
    target = Path(path) if path else config_path()
    if not target.exists():
        raise FileNotFoundError(
            f"Council config not found at {target}. "
            "Set COUNCIL_CONFIG to a valid path, or restore the default."
        )
    with open(target, "r", encoding="utf-8") as fh:
        return json.load(fh)


def reload_council_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Force-reload the council config (clears the LRU cache)."""
    load_council_config.cache_clear()
    return load_council_config(path)


# ---------------------------------------------------------------------------
# Member access
# ---------------------------------------------------------------------------


def list_member_names(cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return all member names defined in the config."""
    cfg = cfg or load_council_config()
    return list(cfg.get("members", {}).keys())


def get_member_config(
    name: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the config dict for a single member, e.g. 'scriptwriter'.

    Raises KeyError if the member is unknown.
    """
    cfg = cfg or load_council_config()
    members = cfg.get("members", {})
    if name not in members:
        raise KeyError(
            f"Unknown council member: {name!r}. "
            f"Available: {sorted(members.keys())}"
        )
    return members[name]


def get_chairman_name(cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return the name of the member marked is_chairman: true, or None."""
    cfg = cfg or load_council_config()
    for name, m in cfg.get("members", {}).items():
        if m.get("is_chairman"):
            return name
    return None


def get_creators(
    cfg: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Members whose output_kind is 'script' or 'design' (the drafters)."""
    cfg = cfg or load_council_config()
    return [
        name
        for name, m in cfg.get("members", {}).items()
        if m.get("output_kind") in ("script", "design")
    ]


def get_reviewers(
    cfg: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Members who have a non-empty 'reviews' list (the reviewers)."""
    cfg = cfg or load_council_config()
    return [
        name
        for name, m in cfg.get("members", {}).items()
        if m.get("reviews")
    ]


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def list_phases(cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return the list of phases. Each phase is a dict with name, members, parallel."""
    cfg = cfg or load_council_config()
    return list(cfg.get("phases", []))


def get_phase(
    name: str,
    cfg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return a single phase by name, or None if not found."""
    for phase in list_phases(cfg):
        if phase.get("name") == name:
            return phase
    return None


# ---------------------------------------------------------------------------
# Behavior settings
# ---------------------------------------------------------------------------


def get_fallback_chain(cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    cfg = cfg or load_council_config()
    return list(cfg.get("fallback_chain", []))


def get_setting(
    key: str,
    default: Any = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Any:
    cfg = cfg or load_council_config()
    return cfg.get(key, default)


def is_enabled(cfg: Optional[Dict[str, Any]] = None) -> bool:
    return bool(get_setting("enabled", True, cfg))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_council_config(cfg: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable validation errors (empty == valid)."""
    errors: List[str] = []
    members = cfg.get("members", {})
    if not members:
        errors.append("config has no 'members' block")
        return errors

    # Members must have model + system_prompt + output_kind
    for name, m in members.items():
        if not m.get("model"):
            errors.append(f"member {name!r} missing 'model'")
        if not m.get("system_prompt"):
            errors.append(f"member {name!r} missing 'system_prompt'")
        if m.get("output_kind") not in ("script", "design", "review", "synthesis", None):
            errors.append(
                f"member {name!r} has invalid output_kind={m.get('output_kind')!r}"
            )

    # 'reviews' must reference existing members
    for name, m in members.items():
        for target in m.get("reviews", []) or []:
            if target not in members:
                errors.append(
                    f"member {name!r} reviews unknown member {target!r}"
                )

    # Phases must reference existing members
    for phase in cfg.get("phases", []):
        for member_name in phase.get("members", []):
            if member_name not in members:
                errors.append(
                    f"phase {phase.get('name')!r} references unknown member {member_name!r}"
                )

    # Exactly one chairman if any synthesis phase is declared
    chairmen = [n for n, m in members.items() if m.get("is_chairman")]
    if len(chairmen) > 1:
        errors.append(f"multiple chairmen declared: {chairmen}")
    return errors
