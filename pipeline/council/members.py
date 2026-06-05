"""The 5 council members.

Each member is a small dataclass holding:
- a name (for logging)
- a role label ("Member A", "Chairman", ...)
- a model id (read from ``council_config.json`` at construction time)
- a temperature (also from the config)
- a system prompt (the role's "personality")
- an output kind: ``script`` | ``design`` | ``review`` | ``synthesis``

The model name is NOT hardcoded here — it comes from
``pipeline/council/council_config.json``. Env vars in the main
``config.py`` (COUNCIL_*_MODEL) override the JSON defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import get_member_config


@dataclass(frozen=True)
class Member:
    name: str
    role_label: str
    model: str
    temperature: float
    system_prompt: str
    output_kind: str
    description: str = ""


# ----- System prompts (these are code, not config — they ARE the role) -----

SCRIPTWRITER_PROMPT = (
    "You are an expert video scriptwriter and curriculum designer. "
    "You convert study documents into structured video scripts. "
    "You focus on the WORDS: scene titles, narration text, and timing. "
    "You do NOT pick visuals, frame styles, or animations — that is "
    "another member's job. You output ONLY valid JSON — no markdown "
    "fences, no preamble, no explanation."
)

VISUAL_DESIGNER_PROMPT = (
    "You are a motion-graphics designer and front-end developer. "
    "You focus on the LOOK: for each scene, you pick a frame style, "
    "an optional diagram primitive, animation primitives, and "
    "highlight words. You do NOT write narration — that is another "
    "member's job. You output ONLY valid JSON — no markdown fences, "
    "no preamble, no explanation."
)

FACT_CHECKER_PROMPT = (
    "You are a research librarian. Your only job is to verify that "
    "every factual claim in the narration is supported by the source "
    "document. For each claim, either cite the source paragraph or "
    "flag it as 'unverified'. Be ruthless — false confidence is worse "
    "than false doubt. You output ONLY valid JSON."
)

PEDAGOGY_REVIEWER_PROMPT = (
    "You are an instructional designer. You review the script for "
    "clarity, pacing (60-120 words per scene), self-containment of "
    "each scene, jargon level (define terms on first use), and "
    "learning flow (does each scene build on the previous?). "
    "You output ONLY valid JSON."
)

CHAIRMAN_PROMPT = (
    "You are the editor-in-chief. You read the scriptwriter's draft, "
    "the visual designer's brief, and the reviews from the "
    "fact-checker and pedagogy reviewer. You produce the FINAL "
    "manifest: scenes with merged script + design + a confidence "
    "score per scene + a plain-English dissent summary. You may "
    "overrule reviewers, but you must record every override. "
    "You output ONLY valid JSON."
)


# Member registry: name -> (role_label, system_prompt, output_kind)
# NOTE: model and temperature come from council_config.json
_MEMBER_DEFS = {
    "scriptwriter": (
        "Member A",
        SCRIPTWRITER_PROMPT,
        "script",
    ),
    "visual_designer": (
        "Member B",
        VISUAL_DESIGNER_PROMPT,
        "design",
    ),
    "fact_checker": (
        "Member C",
        FACT_CHECKER_PROMPT,
        "review",
    ),
    "pedagogy_reviewer": (
        "Member D",
        PEDAGOGY_REVIEWER_PROMPT,
        "review",
    ),
    "chairman": (
        "Chairman",
        CHAIRMAN_PROMPT,
        "synthesis",
    ),
}


def get_member(name: str) -> Member:
    """Look up a single member with model + temperature from council_config.json.

    Raises KeyError if the name is not in the registry.
    """
    if name not in _MEMBER_DEFS:
        raise KeyError(
            f"Unknown council member: {name!r}. "
            f"Available: {sorted(_MEMBER_DEFS.keys())}"
        )
    label, system_prompt, output_kind = _MEMBER_DEFS[name]
    cfg = get_member_config(name)
    return Member(
        name=name,
        role_label=label,
        model=cfg.get("model", ""),
        temperature=float(cfg.get("temperature", 0.4)),
        system_prompt=system_prompt,
        output_kind=output_kind,
        description=cfg.get("description", ""),
    )


def get_members() -> list[Member]:
    """Return all 5 members (creators + reviewers + chairman)."""
    return [get_member(n) for n in _MEMBER_DEFS]


# ----- Anonymization helpers (used by Round 2) -----

ROLE_LABELS = {name: defs[0] for name, defs in _MEMBER_DEFS.items()}


def get_anon_label(member_name: str) -> str:
    """Return the anonymized label for a member, used in Round 2 reviews."""
    return ROLE_LABELS.get(member_name, member_name)


def unanon_label(label: str) -> Optional[str]:
    """Reverse of ``get_anon_label`` — only used by the chairman."""
    for name, anon in ROLE_LABELS.items():
        if anon == label:
            return name
    return None
