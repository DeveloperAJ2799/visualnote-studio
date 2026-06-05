"""The phase-driven orchestrator: runs the council, tracks state, returns the final manifest.

This module knows nothing about PDF ingestion, TTS, or HyperFrames. It
takes (doc_text, doc_title_hint, target_minutes) and returns the
chairman's final manifest + the full council state.

Two implementations:
- ``Council``             — real, calls free models over HTTP.
- ``MockCouncil``         — deterministic, no network, for tests/CI.

Both share the same ``run() -> manifest`` signature so callers can swap
them via ``--mock`` or in tests.

**Phase model.** The council is structured as a list of phases declared
in ``council_config.json``. Each phase has:
  - a name
  - a list of members (in execution order)
  - ``parallel: true|false`` (whether the orchestrator can run them
    concurrently)
  - optional ``skippable: true`` (so ``--council-fast`` can drop it)

The orchestrator walks the phases in order, and within each phase runs
the listed members. A member's role during the run is determined by its
``output_kind`` in the config: ``script`` (drafts the narration),
``design`` (drafts the visuals), ``review`` (peer-reviews other
members), ``synthesis`` (the chairman's final merge).

To add a new member, edit the config. To change a member's behavior,
edit its ``system_prompt`` in the config. To change the council's
deliberation shape, edit ``phases`` in the config. No Python change
needed for any of those.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import CONFIG
from pipeline.council.config import (
    get_fallback_chain,
    list_phases,
    load_council_config,
    validate_council_config,
)
from pipeline.council.llm import CouncilCallResult, CouncilLLMError, chat
from pipeline.council.members import (
    get_anon_label,
    get_member,
    get_members,
)
from pipeline.council.prompts import build_user_prompt
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
    council_config_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], CouncilState]:
    """Run the full phase-driven council and return (final_manifest, state).

    Args:
        doc_text: The full source document text.
        doc_title_hint: Hint for the document title.
        target_minutes: Target video length.
        pdf_hash: Optional cache key.
        fast: If True, skip any phase marked ``skippable: true`` in the
              config (typically the review phase).
        council_config_path: Optional override path to a different
              ``council_config.json``. Lets you swap the entire council
              (members, models, system prompts, phases) for this one run.
    """
    if council_config_path is not None:
        cfg = load_council_config(Path(council_config_path))
    else:
        cfg = load_council_config()
    validation_errors = validate_council_config(cfg)
    if validation_errors:
        log.error("Council config has errors: %s", validation_errors)

    state = CouncilState(
        pdf_hash=pdf_hash,
        doc_text=doc_text,
        doc_title_hint=doc_title_hint,
        target_minutes=target_minutes,
    )
    council = Council()
    manifest = council.run(state, fast=fast, cfg=cfg)
    return manifest, state


# ---------------------------------------------------------------------------
# Real council
# ---------------------------------------------------------------------------


class Council:
    """Runs the phase-driven deliberation against real LLM endpoints."""

    def run(
        self,
        state: CouncilState,
        *,
        fast: bool = False,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cfg = cfg or load_council_config()
        phases = list_phases(cfg)

        if fast:
            phases = [p for p in phases if not p.get("skippable", False)]
            log.info("Council: fast mode, %d phases (skippable dropped)", len(phases))

        log.info(
            "Council starting: doc_title=%r target_min=%d fast=%s phases=%d",
            state.doc_title_hint,
            state.target_minutes,
            fast,
            len(phases),
        )
        run_start = time.perf_counter()

        for phase_idx, phase in enumerate(phases, 1):
            self._run_phase(state, phase, phase_idx, len(phases), cfg)

        log.info(
            "Council complete: %d LLM calls in %.1fs total",
            state.total_calls,
            time.perf_counter() - run_start,
        )

        if state.chairman_output is None:
            log.error("Council: no chairman output; synthesizing fallback manifest")
            state.chairman_output = _fallback_manifest(state)
        return state.chairman_output

    # ----- Phase runner -----

    def _run_phase(
        self,
        state: CouncilState,
        phase: Dict[str, Any],
        phase_idx: int,
        total_phases: int,
        cfg: Dict[str, Any],
    ) -> None:
        name = phase.get("name", f"phase{phase_idx}")
        description = phase.get("description", "")
        member_names = phase.get("members", []) or []
        parallel = bool(phase.get("parallel", True))

        if not member_names:
            log.warning("Phase %d/%d [%s] has no members, skipping", phase_idx, total_phases, name)
            return

        members = [get_member(n, cfg) for n in member_names]
        log.info(
            "Phase %d/%d [%s] (%s): %d members, parallel=%s — %s",
            phase_idx,
            total_phases,
            name,
            ", ".join(m.name for m in members),
            len(members),
            parallel,
            description,
        )

        if parallel and len(members) > 1:
            self._run_members_parallel(state, members, phase_idx)
        else:
            for m in members:
                try:
                    self._do_member(state, m, phase_idx, cfg)
                except Exception as exc:
                    log.error("Phase [%s]: %s raised %s", name, m.name, exc)

    def _run_members_parallel(
        self,
        state: CouncilState,
        members: List[Any],
        phase_idx: int,
    ) -> None:
        with ThreadPoolExecutor(max_workers=len(members)) as pool:
            futures = {
                pool.submit(self._do_member_safe, state, m, phase_idx): m
                for m in members
            }
            for future in as_completed(futures):
                member = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    log.error("Phase: %s failed: %s", member.name, exc)

    def _do_member_safe(self, state: CouncilState, member: Any, phase_idx: int) -> None:
        """Wrapper for ThreadPoolExecutor that swallows exceptions."""
        try:
            self._do_member(state, member, phase_idx, None)
        except Exception as exc:
            log.error("Council %s raised %s", member.name, exc)

    # ----- Single-member execution -----

    def _do_member(
        self,
        state: CouncilState,
        member: Any,
        phase_idx: int,
        cfg: Optional[Dict[str, Any]],
    ) -> MemberCallRecord:
        """Build the user prompt, call the LLM, and stash the parsed output.

        What we do with the parsed output depends on ``output_kind``:
          - ``review``     → wrap in a Review dataclass and append to
                             ``state.reviews``.
          - ``synthesis``  → mirror into ``state.chairman_output`` and
                             store under ``member.name`` in
                             ``state.member_outputs``.
          - everything else (script, design, …) → store under
                             ``member.name`` in ``state.member_outputs``.
        """
        # Build anonymized targets for reviewers
        targets: Optional[List[Dict[str, Any]]] = None
        if member.output_kind == "review":
            targets = [
                {
                    "anon_label": get_anon_label(target_name),
                    "output": state.member_outputs.get(target_name, {}),
                }
                for target_name in member.reviews
            ]

        user_prompt = build_user_prompt(member, state, targets=targets)
        messages = [
            {"role": "system", "content": member.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        record = self._call_member(
            member, phase_idx, member.role or member.output_kind, messages
        )
        state.records.append(record)

        if record.parsed is None:
            log.error(
                "Council %s: no parsed output (text=%dB, error=%s)",
                member.name,
                len(record.text or ""),
                record.error or "JSON parse failed",
            )
            return record

        state.member_outputs[member.name] = record.parsed

        if member.output_kind == "review":
            review = _parsed_to_review(member, targets or [], record)
            state.reviews.append(review)

        if member.is_chairman or member.output_kind == "synthesis":
            state.chairman_output = record.parsed

        return record

    # ----- LLM call helper -----

    def _call_member(
        self,
        member: Any,
        phase_idx: int,
        role: str,
        messages: List[Dict[str, str]],
    ) -> MemberCallRecord:
        log.info(
            "Council call: %s (%s) phase=%d model=%s",
            member.name,
            member.role_label,
            phase_idx,
            member.model,
        )
        record = MemberCallRecord(
            member=member.name,
            model=member.model,
            round=phase_idx,
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

    def run(
        self,
        state: CouncilState,
        *,
        fast: bool = False,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cfg = cfg or load_council_config()
        log.info("MockCouncil starting (no network calls)")

        # Generate a scriptwriter stub from doc_text
        scenes = _mock_split_scenes(state.doc_text, state.target_minutes)
        state.member_outputs["scriptwriter"] = {
            "document_title": state.doc_title_hint,
            "total_scenes": len(scenes),
            "scenes": scenes,
        }

        # Generate a visual-designer stub
        state.member_outputs["visual_designer"] = {
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

        # Skip review phase in fast mode
        if not fast:
            # Find the review phase in the config to know which members to mock
            review_phase = next(
                (p for p in list_phases(cfg) if p.get("name") == "review"),
                None,
            )
            if review_phase:
                for member_name in review_phase.get("members", []):
                    m = get_member(member_name, cfg)
                    if m.output_kind != "review":
                        continue
                    state.reviews.append(
                        Review(
                            member=m.name,
                            target_outputs=[get_anon_label(t) for t in m.reviews],
                            critiques=[
                                Critique(
                                    target_member=get_anon_label("scriptwriter"),
                                    scene_id=s["scene_id"],
                                    verdict="concern",
                                    issues=["[mock] unverified by design"],
                                )
                                for s in scenes
                            ],
                            overall_assessment=f"[mock] {m.name} auto-concern",
                        )
                    )

        # Chairman merges everything
        state.chairman_output = _build_merged_manifest(
            state, low_confidence_all=True, confidence=0.5
        )
        state.member_outputs["chairman"] = state.chairman_output
        log.info("MockCouncil done: %d scenes", len(scenes))
        return state.chairman_output


# ---------------------------------------------------------------------------
# Review-parsing helper (used by both real and mock councils)
# ---------------------------------------------------------------------------


def _parsed_to_review(
    member: Any,
    targets: List[Dict[str, Any]],
    record: MemberCallRecord,
) -> Review:
    """Convert a parsed reviewer output into a typed ``Review``."""
    parsed = record.parsed if isinstance(record.parsed, dict) else {}
    critiques: List[Critique] = []
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
    return Review(
        member=member.name,
        target_outputs=[t.get("anon_label", "?") for t in targets],
        critiques=critiques,
        overall_assessment=str(parsed.get("overall_assessment", "")),
        elapsed_s=record.elapsed_s,
    )


# ---------------------------------------------------------------------------
# Helpers (mock + fallback)
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
        while len(paragraphs) < target_scenes:
            paragraphs.append(paragraphs[len(paragraphs) % len(paragraphs)])
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
        scenes.append(
            {
                "scene_id": i + 1,
                "title": title,
                "narration": narration,
                "duration_hint_s": max(20, int(word_count / 2.3)),
                "visual_type": "title_card",
                "manim_prompt": None,
                "image_query": None,
                "html_content": None,
            }
        )
    return scenes


def _fallback_manifest(state: CouncilState) -> Dict[str, Any]:
    """Last-ditch manifest when even the chairman fails."""
    return _build_merged_manifest(state, low_confidence_all=True, confidence=0.3)


def _build_merged_manifest(
    state: CouncilState,
    *,
    low_confidence_all: bool,
    confidence: float,
) -> Dict[str, Any]:
    """Merge scriptwriter + visual_designer into the chairman's output shape."""
    sw = state.member_outputs.get("scriptwriter", {}) or {}
    vd = state.member_outputs.get("visual_designer", {}) or {}
    designs_by_id = {
        d.get("scene_id"): d for d in vd.get("scene_designs", []) or []
    }

    threshold = CONFIG.council_confidence_threshold
    scenes: List[Dict[str, Any]] = []
    for s in sw.get("scenes", []) or []:
        sid = s.get("scene_id")
        d = designs_by_id.get(sid, {})
        frame_style = d.get("frame_style", "text_only")
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
    """Persist the final manifest + per-member outputs for caching."""
    if not state.pdf_hash:
        return
    if state.chairman_output is not None:
        _cache_path(state.pdf_hash, "council_manifest").write_text(
            json.dumps(state.chairman_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    for member_name, output in state.member_outputs.items():
        if output is None:
            continue
        _cache_path(state.pdf_hash, f"member_{member_name}").write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
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
