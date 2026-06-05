"""Member definitions loaded from the council config.

The Python file contains NO hardcoded member names, system prompts, or
roles. Everything comes from ``council_config.json``. The dataclass
``Member`` is just a typed view of one entry in that file.

To add a new member, edit the JSON. To change a member's behavior, edit
its ``system_prompt`` in the JSON. To change which models speak for which
role, edit the ``model`` field. The orchestrator discovers members via
``get_members()`` and respects whatever is in the config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .config import (
    get_chairman_name,
    get_member_config,
    list_member_names,
    load_council_config,
)


@dataclass(frozen=True)
class Member:
    """One council member. All fields are read from the config file."""

    name: str
    role_label: str
    model: str
    temperature: float
    system_prompt: str
    output_kind: str
    role: str = ""
    description: str = ""
    reviews: List[str] = field(default_factory=list)
    is_chairman: bool = False


def get_member(name: str, cfg: Optional[dict] = None) -> Member:
    """Look up a single member by name. All fields come from the config.

    Env vars override the config:
    - COUNCIL_<NAME>_MODEL  → overrides ``model``
    - COUNCIL_<NAME>_TEMPERATURE → overrides ``temperature``
    """
    import os
    if cfg is None:
        cfg = load_council_config()
    raw = get_member_config(name, cfg)
    env_model = os.getenv(f"COUNCIL_{name.upper()}_MODEL")
    env_temp = os.getenv(f"COUNCIL_{name.upper()}_TEMPERATURE")
    return Member(
        name=name,
        role_label=raw.get("label", name),
        model=env_model or raw.get("model", ""),
        temperature=float(env_temp) if env_temp else float(raw.get("temperature", 0.4)),
        system_prompt=raw.get("system_prompt", ""),
        output_kind=raw.get("output_kind", ""),
        role=raw.get("role", ""),
        description=raw.get("description", ""),
        reviews=list(raw.get("reviews", []) or []),
        is_chairman=bool(raw.get("is_chairman", False)),
    )


def get_members(cfg: Optional[dict] = None) -> List[Member]:
    """Return ALL members declared in the config, in config order."""
    if cfg is None:
        cfg = load_council_config()
    return [get_member(name, cfg) for name in list_member_names(cfg)]


def get_chairman(cfg: Optional[dict] = None) -> Optional[Member]:
    """Return the member flagged is_chairman, or None."""
    if cfg is None:
        cfg = load_council_config()
    name = get_chairman_name(cfg)
    if not name:
        return None
    return get_member(name, cfg)


def get_creators(cfg: Optional[dict] = None) -> List[Member]:
    """Return members that produce primary outputs (script or design)."""
    return [
        m for m in get_members(cfg)
        if m.output_kind in ("script", "design")
    ]


def get_reviewers(cfg: Optional[dict] = None) -> List[Member]:
    """Return members that have a non-empty 'reviews' list."""
    return [m for m in get_members(cfg) if m.reviews]


# ---------------------------------------------------------------------------
# Anonymization helpers (used by Round 2)
# ---------------------------------------------------------------------------


def get_anon_labels(cfg: Optional[dict] = None) -> dict:
    """Return {member_name: anon_label} for every member, from the config."""
    if cfg is None:
        cfg = load_council_config()
    return {
        name: raw.get("label", name)
        for name, raw in cfg.get("members", {}).items()
    }


def get_anon_label(member_name: str, cfg: Optional[dict] = None) -> str:
    return get_anon_labels(cfg).get(member_name, member_name)


def unanon_label(label: str, cfg: Optional[dict] = None) -> Optional[str]:
    for name, anon in get_anon_labels(cfg).items():
        if anon == label:
            return name
    return None
