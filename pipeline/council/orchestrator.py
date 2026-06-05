"""The 3-round orchestrator: runs the council, tracks state, returns the final manifest.

This module knows nothing about PDF ingestion, TTS, or HyperFrames. It
takes (doc_text, doc_title_hint, target_minutes) and returns the
chairman's final manifest + the full council state.

Two implementations:
- ``Council``             — real, calls free models over HTTP.
- ``MockCouncil``         — deterministic, no network, for tests/CI.

Both share the same ``run() -> (manifest, state)`` signature so callers
can swap them via ``--mock`` or in tests.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import CONFIG
from pipeline.council.config import get_fallback_chain
from pipeline.council.llm import CouncilLLMError, CouncilCallResult, chat
from pipeline.council.members import (
    get_member,
    get_members,
    get_anon_label,
)
from pipeline.council.prompts import (
    chairman_user,
    review_user,
    scriptwriter_user,
    visual_designer_user,
)
from pipeline.council.state import (
    CouncilState,
    Critique,
    MemberCallRecord,
    Review,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_council(
    doc_text: str,
    doc_title_hint: str,
    *,
    target_minutes: int = 10,
    pdf_hash: str = "",
    fast: bool = False,
) -> Tuple[Dict[str, Any], CouncilState]:
    """Run the full 3-round council and return (final_manifest, state).

    Args:
        doc_text: The full source document text.
        doc_title_hint: Hint for the document title.
        target_minutes: Target video length.
        pdf_hash: Optional cache key.
        fast: If True, skip Round 2 reviews (3 calls instead of 9).
              The chairman still synthesizes; reviews are empty.
    """
    state = CouncilState(
        pdf_hash=pdf_hash,
        doc_text=doc_text,
        doc_title_hint=doc_title_hint,
        target_minutes=target_minutes,
    )
    council = Council()
    manifest = council.run(state, fast=fast)
    return manifest, state


# ---------------------------------------------------------------------------
# Real council
# ---------------------------------------------------------------------------


class Council:
    """Runs the 3-round deliberation against real LLM endpoints."""

    def run(self, state: CouncilState, *, fast: bool = False) -> Dict[str, Any]:
        log.info(
            "Council starting: doc_title=%r target_min=%d fast=%s",
            state.doc_title_hint, state.target_minutes, fast,
        )
        round_start = time.perf_counter()

        # ---- Round 1: parallel generation ----
        log.info("Council round 1/3: 2 parallel creator calls")
        self._round1(state)
        log.info(
            "Council round 1 done in %.1fs (calls=%d, total elapsed=%.1fs)",
            time.perf_counter() - round_start, state.total_calls, state.total_elapsed_s,
        )

        # ---- Round 2: parallel reviews (skipped in fast mode) ----
        if not fast:
            log.info("Council round 2/3: 4 parallel peer-review calls")
            self._round2(state)
            log.info(
                "Council round 2 done in %.1fs (calls=%d, total elapsed=%.1fs)",
                time.perf_counter() - round_start, state.total_calls, state.total_elapsed_s,
            )
        else:
            log.info("Council round 2/3: skipped (--council-fast)")

        # ---- Round 3: chairman synthesis ----
        log.info("Council round 3/3: chairman synthesis")
        self._round3(state)
        log.info(
            "Council complete: %d LLM calls in %.1fs total",
            state.total_calls, state.total_elapsed_s,
        )

        if state.chairman_output is None:
            raise RuntimeError("Council: chairman produced no output")
        return state.chairman_output

    # ----- Round 1: 2 creators in parallel -----

    def _round1(self, state: CouncilState) -> None:
        scriptwriter = get_member("scriptwriter")
        visual_designer = get_member("visual_designer")

        sw_messages = [
            {"role": "system", "content": scriptwriter.system_prompt},
            {
                "role": "user",
                "content": scriptwriter_user(
                    state.doc_text, state.doc_title_hint, state.target_minutes
                ),
            },
        ]
        # Visual designer will need the scriptwriter output, so we run
        # them sequentially. The scriptwriter is faster (StepFun), so the
        # sequential overhead is minimal vs. the model latency.
        sw_record = self._call_member(scriptwriter, 1, "creator", sw_messages)
        state.scriptwriter_output = sw_record.parsed

        if state.scriptwriter_output is None:
            log.error("Scriptwriter returned no parseable JSON; using empty stub")
            state.scriptwriter_output = {
                "document_title": state.doc_title_hint,
                "total_scenes": 0,
                "scenes": [],
            }

        vd_messages = [
            {"role": "system", "content": visual_designer.system_prompt},
            {
                "role": "user",
                "content": visual_designer_user(
                    state.doc_text,
                    state.doc_title_hint,
                    state.scriptwriter_output,
                ),
            },
        ]
        vd_record = self._call_member(visual_designer, 1, "creator", vd_messages)
        state.visual_designer_output = vd_record.parsed

        if state.visual_designer_output is None:
            log.error("Visual Designer returned no parseable JSON; using empty stub")
            state.visual_designer_output = {"scene_designs": []}

    # ----- Round 2: 4 reviewers in parallel -----

    def _round2(self, state: CouncilState) -> None:
        # Build the 4 review tasks
        scriptwriter = get_member("scriptwriter")
        visual_designer = get_member("visual_designer")
        fact_checker = get_member("fact_checker")
        pedagogy_reviewer = get_member("pedagogy_reviewer")

        # Anonymize the round-1 outputs
        anon_script = {
            "anon_label": get_anon_label("scriptwriter"),
            "output": state.scriptwriter_output or {},
        }
        anon_design = {
            "anon_label": get_anon_label("visual_designer"),
            "output": state.visual_designer_output or {},
        }

        tasks = [
            (
                scriptwriter,
                [anon_design],  # scriptwriter reviews the designer's output
                "creator",
            ),
            (
                visual_designer,
                [anon_script],  # designer reviews the scriptwriter's output
                "creator",
            ),
            (
                fact_checker,
                [anon_script, anon_design],
                "reviewer",
            ),
            (
                pedagogy_reviewer,
                [anon_script, anon_design],
                "reviewer",
            ),
        ]

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(self._do_review, member, targets, state): member
                for member, targets, _ in tasks
            }
            for future in as_completed(futures):
                member = futures[future]
                try:
                    review = future.result()
                    state.reviews.append(review)
                except Exception as exc:
                    log.error("Reviewer %s failed: %s", member.name, exc)
                    # Record a stub review so the chairman can still see
                    # the member tried.
                    state.reviews.append(
                        Review(
                            member=member.name,
                            target_outputs=[t["anon_label"] for t in ([anon_script, anon_design] if member.name in ("fact_checker", "pedagogy_reviewer") else [anon_design if member.name == "scriptwriter" else anon_script])],
                            overall_assessment=f"Review failed: {exc}",
                        )
                    )

    def _do_review(
        self,
        member,
        targets: List[Dict[str, Any]],
        state: CouncilState,
    ) -> Review:
        messages = [
            {"role": "system", "content": member.system_prompt},
            {
                "role": "user",
                "content": review_user(member.name, targets, state.doc_text),
            },
        ]
        record = self._call_member(member, 2, "reviewer", messages)
        parsed = record.parsed
        critiques: List[Critique] = []
        overall = ""
        if isinstance(parsed, dict):
            for c in parsed.get("reviews", []) or []:
                try:
                    critiques.append(
                        Critique(
                            target_member=str(c.get("target_member", "")),
                            scene_id=int(c.get("scene_id", 0) or 0),
                            verdict=str(c.get("verdict", "concern")).lower(),
                            issues=list(c.get("issues", []) or []),
                            suggested_fix=str(c.get("suggested_fix", "")),
                        )
                    )
                except Exception as exc:
                    log.warning("Bad critique from %s: %s", member.name, exc)
            overall = str(parsed.get("overall_assessment", ""))
        return Review(
            member=member.name,
            target_outputs=[t.get("anon_label", "?") for t in targets],
            critiques=critiques,
            overall_assessment=overall,
            elapsed_s=record.elapsed_s,
        )

    # ----- Round 3: chairman synthesis -----

    def _round3(self, state: CouncilState) -> None:
        chairman = get_member("chairman")
        reviews_for_chairman = [
            {
                "member": r.member,
                "target_outputs": r.target_outputs,
                "critiques": [
                    {
                        "target_member": c.target_member,
                        "scene_id": c.scene_id,
                        "verdict": c.verdict,
                        "issues": c.issues,
                        "suggested_fix": c.suggested_fix,
                    }
                    for c in r.critiques
                ],
                "overall_assessment": r.overall_assessment,
            }
            for r in state.reviews
        ]
        messages = [
            {"role": "system", "content": chairman.system_prompt},
            {
                "role": "user",
                "content": chairman_user(
                    state.doc_text,
                    state.doc_title_hint,
                    state.target_minutes,
                    state.scriptwriter_output or {},
                    state.visual_designer_output or {},
                    reviews_for_chairman,
                ),
            },
        ]
        record = self._call_member(chairman, 3, "chairman", messages)
        state.chairman_output = record.parsed
        if state.chairman_output is None:
            # Last-ditch: synthesize a minimal manifest from the scriptwriter output
            log.error("Chairman produced no JSON; synthesizing fallback manifest")
            state.chairman_output = _fallback_manifest(state)

    # ----- LLM call helper -----

    def _call_member(
        self,
        member,
        round_num: int,
        role: str,
        messages: List[Dict[str, str]],
    ) -> MemberCallRecord:
        log.info(
            "Council call: %s (%s) round=%d model=%s",
            member.name, member.role_label, round_num, member.model,
        )
        record = MemberCallRecord(
            member=member.name,
            model=member.model,
            round=round_num,
            role=role,
        )
        try:
            result: CouncilCallResult = chat(
                base_url=CONFIG.kilo_base_url,
                api_key=CONFIG.kilo_api_key,
                model=member.model,
                messages=messages,
                json_mode=True,
                temperature=member.temperature,
                max_retries=CONFIG.council_max_retries,
                fallback_models=get_fallback_chain(),
            )
            record.text = result.text
            record.model = result.model
            record.elapsed_s = result.elapsed_s
            record.fallback_used = result.fallback_used
            # `chat` with json_mode=True returns JSON-stringified parsed output
            try:
                record.parsed = json.loads(result.text)
            except json.JSONDecodeError as exc:
                record.parse_error = str(exc)
                log.warning("Council %s: JSON parse failed: %s", member.name, exc)
        except CouncilLLMError as exc:
            record.error = str(exc)
            log.error("Council %s: LLM call failed: %s", member.name, exc)
        return record


# ---------------------------------------------------------------------------
# Mock council (no network, deterministic)
# ---------------------------------------------------------------------------


class MockCouncil:
    """Deterministic council for offline / CI runs.

    Produces a valid manifest from the scriptwriter stub plus
    reasonable defaults for the design and reviews. All members report
    ``confidence=0.5`` and every scene is marked ``low_confidence: true``.
    """

    def run(self, state: CouncilState, *, fast: bool = False) -> Dict[str, Any]:
        log.info("MockCouncil starting (no network calls)")

        # Mock scriptwriter: split doc_text into roughly equal narration chunks
        scenes = _mock_split_scenes(state.doc_text, state.target_minutes)
        state.scriptwriter_output = {
            "document_title": state.doc_title_hint,
            "total_scenes": len(scenes),
            "scenes": scenes,
        }

        # Mock visual designer: pick a varied frame_style per scene
        state.visual_designer_output = {
            "scene_designs": [
                {
                    "scene_id": s["scene_id"],
                    "frame_style": _mock_pick_frame_style(i, len(scenes)),
                    "diagram": None,
                    "animations": [],
                    "highlights": [],
                    "rationale": "[mock] auto-picked",
                }
                for i, s in enumerate(scenes)
            ]
        }

        # Mock reviews: every scene gets a "concern" (mock mode = uncertain)
        if not fast:
            state.reviews = [
                Review(
                    member="fact_checker",
                    target_outputs=["Member A", "Member B"],
                    critiques=[
                        Critique(
                            target_member="Member A",
                            scene_id=s["scene_id"],
                            verdict="concern",
                            issues=["[mock] unverified by design"],
                        )
                        for s in scenes
                    ],
                    overall_assessment="[mock] all claims unverified",
                ),
                Review(
                    member="pedagogy_reviewer",
                    target_outputs=["Member A", "Member B"],
                    critiques=[
                        Critique(
                            target_member="Member A",
                            scene_id=s["scene_id"],
                            verdict="approve",
                            issues=[],
                        )
                        for s in scenes
                    ],
                    overall_assessment="[mock] pacing acceptable",
                ),
            ]

        # Mock chairman: merge and mark all low_confidence
        state.chairman_output = _build_merged_manifest(
            state, low_confidence_all=True, confidence=0.5,
        )
        log.info("MockCouncil done: %d scenes", len(scenes))
        return state.chairman_output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FRAME_STYLE_CYCLE = [
    "title_hero",
    "image_left",
    "diagram_center",
    "split_compare",
    "quote_callout",
    "text_only",
]


def _mock_pick_frame_style(idx: int, total: int) -> str:
    """Pick a varied frame style per scene; first and last are title_hero."""
    if idx == 0 or idx == total - 1:
        return "title_hero"
    return _FRAME_STYLE_CYCLE[idx % len(_FRAME_STYLE_CYCLE)]


def _mock_split_scenes(doc_text: str, target_minutes: int) -> List[Dict[str, Any]]:
    """Naively split the document into ~target_scenes narration chunks."""
    target_scenes = max(4, target_minutes * 2)
    paragraphs = [p.strip() for p in doc_text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [doc_text[:500]] if doc_text else ["[mock] empty document"]
    if len(paragraphs) <= target_scenes:
        # Reuse paragraphs to reach the count
        while len(paragraphs) < target_scenes:
            paragraphs.append(paragraphs[len(paragraphs) % len(paragraphs)])
    # Group paragraphs into scenes (~equal number of paragraphs per scene)
    per_scene = max(1, len(paragraphs) // target_scenes)
    scenes: List[Dict[str, Any]] = []
    for i in range(target_scenes):
        start = i * per_scene
        end = start + per_scene if i < target_scenes - 1 else len(paragraphs)
        chunk = " ".join(paragraphs[start:end])
        title = (
            f"Scene {i + 1}: {chunk[:50].strip().rstrip('.').rstrip(',')}..."
            if len(chunk) > 50
            else f"Scene {i + 1}"
        )
        narration = chunk[:600] if chunk else "[mock] placeholder narration."
        word_count = max(1, len(narration.split()))
        scenes.append({
            "scene_id": i + 1,
            "title": title,
            "narration": narration,
            "duration_hint_s": max(20, int(word_count / 2.3)),
            "visual_type": "title_card",
            "manim_prompt": None,
            "image_query": None,
            "html_content": None,
        })
    return scenes


def _fallback_manifest(state: CouncilState) -> Dict[str, Any]:
    """Last-ditch manifest when even the chairman fails."""
    sw = state.scriptwriter_output or {}
    scenes = sw.get("scenes", [])
    return _build_merged_manifest(state, low_confidence_all=True, confidence=0.3)


def _build_merged_manifest(
    state: CouncilState,
    *,
    low_confidence_all: bool,
    confidence: float,
) -> Dict[str, Any]:
    """Merge scriptwriter + visual_designer into the chairman's output shape."""
    sw = state.scriptwriter_output or {}
    vd = state.visual_designer_output or {}
    designs_by_id = {
        d.get("scene_id"): d for d in vd.get("scene_designs", []) or []
    }

    threshold = CONFIG.council_confidence_threshold
    scenes: List[Dict[str, Any]] = []
    for s in sw.get("scenes", []) or []:
        sid = s.get("scene_id")
        d = designs_by_id.get(sid, {})
        frame_style = d.get("frame_style", "text_only")
        # Map frame_style to legacy visual_type for downstream compatibility
        vt = _frame_to_visual_type(frame_style)
        merged = {
            "scene_id": sid,
            "title": s.get("title", ""),
            "narration": s.get("narration", ""),
            "duration_hint_s": int(s.get("duration_hint_s", 30) or 30),
            "visual_type": vt,
            "manim_prompt": s.get("manim_prompt"),
            "image_query": s.get("image_query"),
            "html_content": s.get("html_content"),
            "frame_style": frame_style,
            "diagram": d.get("diagram"),
            "animations": d.get("animations", []) or [],
            "highlights": d.get("highlights", []) or [],
            "confidence": confidence,
            "low_confidence": low_confidence_all or confidence < threshold,
            "chairman_override": False,
        }
        scenes.append(merged)

    return {
        "document_title": sw.get("document_title", state.doc_title_hint),
        "total_scenes": len(scenes),
        "scenes": scenes,
        "dissent_summary": state.dissent_summary(),
        "confidence_overall": confidence,
    }


def _frame_to_visual_type(frame_style: str) -> str:
    """Map the designer's frame_style to the legacy visual_type enum."""
    if frame_style in ("text_only", "quote_callout", "title_hero"):
        return "title_card"
    if frame_style in ("image_left", "diagram_center", "split_compare"):
        return "manim_animation"
    return "title_card"


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _cache_path(pdf_hash: str, suffix: str) -> Path:
    cache_dir = CONFIG.output_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{pdf_hash}_{suffix}.json"


def save_council_cache(state: CouncilState) -> None:
    """Persist the final manifest + per-round outputs for caching."""
    if not state.pdf_hash:
        return
    if state.chairman_output is not None:
        _cache_path(state.pdf_hash, "council_manifest").write_text(
            json.dumps(state.chairman_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if state.scriptwriter_output is not None:
        _cache_path(state.pdf_hash, "round1_script").write_text(
            json.dumps(state.scriptwriter_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if state.visual_designer_output is not None:
        _cache_path(state.pdf_hash, "round1_design").write_text(
            json.dumps(state.visual_designer_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_council_cache(pdf_hash: str) -> Optional[Dict[str, Any]]:
    """Return the cached chairman manifest for `pdf_hash`, or None."""
    if not pdf_hash:
        return None
    path = _cache_path(pdf_hash, "council_manifest")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Council cache unreadable: %s", exc)
        return None
