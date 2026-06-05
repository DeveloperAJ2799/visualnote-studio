"""Dataclasses for council state.

These are the typed containers that move between rounds. Every council call
returns a ``MemberCallRecord``; the orchestrator collects them into
``CouncilState`` and the chairman reads from it.

All member outputs are stored in ``CouncilState.member_outputs`` keyed by
member name. The chairman's final manifest is also mirrored on
``chairman_output`` for convenience.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemberCallRecord:
    """Record of a single LLM call by a council member."""

    member: str
    model: str
    round: int
    role: str  # "creator" | "reviewer" | "chairman"
    text: str = ""
    parsed: Optional[Any] = None
    parse_error: Optional[str] = None
    elapsed_s: float = 0.0
    fallback_used: bool = False
    error: Optional[str] = None


@dataclass
class Critique:
    """One review verdict from a Round-2 member."""

    target_member: str  # "Member A" | "Member B" | "Member C" | "Member D"
    scene_id: int
    verdict: str  # "approve" | "concern" | "reject"
    issues: List[str] = field(default_factory=list)
    suggested_fix: str = ""


@dataclass
class Review:
    """A member's full Round-2 output: a list of critiques + an overall note."""

    member: str
    target_outputs: List[str]  # member labels this reviewer was shown
    critiques: List[Critique] = field(default_factory=list)
    overall_assessment: str = ""
    elapsed_s: float = 0.0


@dataclass
class CouncilState:
    """The full state of one council run.

    All member outputs are stored in ``member_outputs`` keyed by member
    name. The chairman's final manifest is mirrored on ``chairman_output``
    for callers that don't want to dig into ``member_outputs``.
    """

    pdf_hash: str
    doc_text: str
    doc_title_hint: str
    target_minutes: int = 10

    # Generic storage: every member's parsed output is stored here,
    # keyed by member name (e.g. "scriptwriter", "visual_designer",
    # "fact_checker", "pedagogy_reviewer", "chairman").
    member_outputs: Dict[str, Any] = field(default_factory=dict)

    # Reviews collected in the review phase (only members with
    # output_kind == "review" produce entries here).
    reviews: List[Review] = field(default_factory=list)

    # Chairman's final merged manifest, mirrored from member_outputs["chairman"]
    # for convenience.
    chairman_output: Optional[Dict[str, Any]] = None

    # Telemetry
    records: List[MemberCallRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Convenience accessors (read-only views into member_outputs)
    # ------------------------------------------------------------------

    @property
    def scriptwriter_output(self) -> Optional[Dict[str, Any]]:
        return self.member_outputs.get("scriptwriter")

    @property
    def visual_designer_output(self) -> Optional[Dict[str, Any]]:
        return self.member_outputs.get("visual_designer")

    @property
    def total_calls(self) -> int:
        return len(self.records)

    @property
    def total_elapsed_s(self) -> float:
        return sum(r.elapsed_s for r in self.records)

    def dissent_summary(self) -> str:
        """Plain-English one-liner summarizing any flags from reviewers."""
        flags: List[str] = []
        for review in self.reviews:
            for c in review.critiques:
                if c.verdict == "reject":
                    flags.append(
                        f"{review.member} rejected scene {c.scene_id}: {c.issues[0] if c.issues else 'no reason given'}"
                    )
                elif c.verdict == "concern":
                    flags.append(
                        f"{review.member} flagged scene {c.scene_id}: {c.issues[0] if c.issues else 'no reason given'}"
                    )
        if not flags:
            return "No reviewer flags. All scenes approved."
        return f"{len(flags)} reviewer flags: " + " | ".join(flags[:5])
