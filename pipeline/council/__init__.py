"""Multi-member council for scene manifest generation.

The council replaces the single-LLM manifest call with a 3-round deliberation:
  - Round 1: Scriptwriter + Visual Designer generate the script and design.
  - Round 2: Fact-Checker + Pedagogy Reviewer (and cross-reviews by the
    creators) review each other's work, with anonymized labels.
  - Round 3: Chairman synthesizes the final manifest + dissent summary.

Use ``run_council(doc_text, doc_title_hint, target_minutes=...)`` for the
real implementation, or pass ``--mock`` to the CLI for a deterministic
``MockCouncil`` that makes no network calls.
"""
from __future__ import annotations

from .orchestrator import (
    Council,
    MockCouncil,
    load_council_cache,
    run_council,
    save_council_cache,
)
from .state import CouncilState, Critique, MemberCallRecord, Review

__all__ = [
    "Council",
    "CouncilState",
    "Critique",
    "MemberCallRecord",
    "MockCouncil",
    "Review",
    "load_council_cache",
    "run_council",
    "save_council_cache",
]
