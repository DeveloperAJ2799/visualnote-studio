"""Scene manifest generation.

By default, uses the single-LLM path (1 call, fast) against the supplied
``MiMoClient``. Pass ``use_council=True`` (or set CONFIG.council_enabled
to True) to use the 5-member council (3-5 calls, slower but more thorough).

The output is validated against the PRD §8 schema, repaired if possible,
and saved to `output/scene_manifest.json`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import CONFIG
from pipeline.clients.base import MiMoClient

log = logging.getLogger(__name__)

ALLOWED_VISUAL_TYPES = {
    "manim_animation",
    "html_frame",
    "image_overlay",
    "title_card",
    "mixed",
}

# Council-produced scenes carry extra fields the renderer can use.
COUNCIL_SCENE_EXTRA_KEYS = {
    "frame_style",
    "diagram",
    "animations",
    "highlights",
    "confidence",
    "low_confidence",
    "chairman_override",
}

REQUIRED_SCENE_KEYS = {
    "scene_id",
    "title",
    "narration",
    "duration_hint_s",
    "visual_type",
    "manim_prompt",
    "image_query",
    "html_content",
}

REQUIRED_TOP_KEYS = {"document_title", "total_scenes", "scenes"}


def _validate_manifest(manifest: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable validation errors (empty == valid)."""
    errors: List[str] = []
    missing_top = REQUIRED_TOP_KEYS - manifest.keys()
    if missing_top:
        errors.append(f"missing top-level keys: {sorted(missing_top)}")
        return errors
    scenes = manifest.get("scenes") or []
    if not isinstance(scenes, list):
        errors.append("'scenes' must be a list")
        return errors
    if manifest.get("total_scenes") != len(scenes):
        errors.append(
            f"total_scenes={manifest.get('total_scenes')} does not match len(scenes)={len(scenes)}"
        )
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            errors.append(f"scene[{i}] is not a dict")
            continue
        missing = REQUIRED_SCENE_KEYS - scene.keys()
        if missing:
            errors.append(f"scene[{i}] missing keys: {sorted(missing)}")
        vt = scene.get("visual_type")
        if vt not in ALLOWED_VISUAL_TYPES:
            errors.append(
                f"scene[{i}] has invalid visual_type={vt!r}; allowed={sorted(ALLOWED_VISUAL_TYPES)}"
            )
        narr = scene.get("narration")
        if not isinstance(narr, str) or not narr.strip():
            errors.append(f"scene[{i}] has empty narration")
        dur = scene.get("duration_hint_s")
        if not isinstance(dur, (int, float)) or dur <= 0:
            errors.append(f"scene[{i}] has invalid duration_hint_s={dur!r}")
    return errors


def _repair_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort repair of common LLM mistakes without changing scene count."""
    for scene in manifest.get("scenes", []) or []:
        if scene.get("visual_type") not in ALLOWED_VISUAL_TYPES:
            scene["visual_type"] = "title_card"
            scene["manim_prompt"] = None
            scene["html_content"] = None
        if not scene.get("title"):
            scene["title"] = "Untitled Scene"
        if not scene.get("narration"):
            scene["narration"] = "Placeholder narration for this scene."
        if not isinstance(scene.get("duration_hint_s"), (int, float)) or scene["duration_hint_s"] <= 0:
            word_count = max(1, len(scene["narration"].split()))
            scene["duration_hint_s"] = max(15, int(word_count / 2.3))
        vt = scene.get("visual_type")
        if vt in {"manim_animation", "mixed"} and not scene.get("manim_prompt"):
            scene["manim_prompt"] = (
                f"Show a clear, labeled diagram illustrating: {scene.get('title','this concept')}."
            )
        if vt == "html_frame" and not scene.get("html_content"):
            scene["html_content"] = "callout"
        if not scene.get("image_query"):
            scene["image_query"] = None
    if "total_scenes" not in manifest or manifest["total_scenes"] != len(
        manifest.get("scenes", [])
    ):
        manifest["total_scenes"] = len(manifest.get("scenes", []))
    if not manifest.get("document_title"):
        manifest["document_title"] = "Untitled Document"
    return manifest


def _build_doc_text(doc_content: Dict[str, Any], max_chars: int = 40_000) -> str:
    """Flatten the doc_content into a single text blob for the LLM, truncating if needed."""
    chunks: List[str] = []
    title = doc_content.get("document_title") or ""
    if title:
        chunks.append(f"# {title}\n")
    for section in doc_content.get("sections", []):
        heading = section.get("heading")
        if heading:
            chunks.append(f"\n## {heading}\n")
        for block in section.get("blocks", []):
            if block.get("type") == "text":
                chunks.append(block.get("text", ""))
    text = "\n".join(chunks).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[document truncated for prompt size]"
    return text


def generate_manifest(
    doc_content: Dict[str, Any],
    client: MiMoClient,
    max_scenes: Optional[int] = None,
    *,
    use_council: Optional[bool] = None,
    target_minutes: int = 10,
    fast: bool = False,
    council_config: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run scene manifest generation. By default uses the 5-member council.

    Args:
        doc_content: Parsed PDF content.
        client: A MiMoClient. Used only when the council is disabled or
            falls back to the legacy path.
        max_scenes: Optional cap on the number of scenes.
        use_council: If None, read CONFIG.council_enabled. If True/False,
            force on/off.
        target_minutes: Used by the council to size the manifest.
        fast: If True, the council skips Round 2 (faster but lower quality).
        council_config: Optional path to a custom ``council_config.json``
            to use for this run. Lets you swap members, models, system
            prompts, and phase structure without touching Python.

    Raises:
        RuntimeError: If validation still fails after repair + retry.
    """
    if use_council is None:
        use_council = CONFIG.council_enabled

    doc_text = _build_doc_text(doc_content)
    title_hint = doc_content.get("document_title", "Untitled Document")

    if use_council:
        manifest = _generate_manifest_via_council(
            doc_text=doc_text,
            title_hint=title_hint,
            target_minutes=target_minutes,
            fast=fast,
            council_config_path=council_config,
        )
    else:
        manifest = _generate_manifest_legacy(
            doc_text=doc_text,
            title_hint=title_hint,
            client=client,
        )

    # Validate + repair the final manifest (council or legacy)
    errors = _validate_manifest(manifest)
    if errors:
        log.warning("Manifest validation issues; attempting repair: %s", errors[:3])
        manifest = _repair_manifest(manifest)
        errors = _validate_manifest(manifest)
    if errors:
        raise RuntimeError(
            "Scene manifest failed validation after repair: "
            + "; ".join(errors)
        )

    if max_scenes is not None and len(manifest["scenes"]) > max_scenes:
        manifest["scenes"] = manifest["scenes"][:max_scenes]
        manifest["total_scenes"] = len(manifest["scenes"])

    log.info(
        "Generated manifest: %d scenes, types=%s",
        len(manifest["scenes"]),
        sorted({s["visual_type"] for s in manifest["scenes"]}),
    )
    return manifest


def _generate_manifest_via_council(
    *,
    doc_text: str,
    title_hint: str,
    target_minutes: int,
    fast: bool,
    council_config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run the 5-member council. Falls back to legacy on hard failure."""
    from pipeline.council import run_council, save_council_cache

    log.info(
        "Generating manifest via council (target_min=%d, fast=%s, config=%s)",
        target_minutes, fast, council_config_path or "<default>",
    )
    try:
        manifest, state = run_council(
            doc_text=doc_text,
            doc_title_hint=title_hint,
            target_minutes=target_minutes,
            pdf_hash=_pdf_hash(title_hint, doc_text),
            fast=fast,
            council_config_path=council_config_path,
        )
        # Cache the final manifest + per-member outputs
        save_council_cache(state)
        # Log dissent
        if manifest.get("dissent_summary"):
            log.info("Council dissent: %s", manifest["dissent_summary"])
        return manifest
    except Exception as exc:
        log.error("Council failed (%s); cannot fall back without a client", exc)
        raise


def _generate_manifest_legacy(
    *,
    doc_text: str,
    title_hint: str,
    client: MiMoClient,
) -> Dict[str, Any]:
    """Legacy single-LLM path. Used when --no-council is set."""
    log.info("Generating scene manifest (legacy single-LLM, text length=%d)", len(doc_text))
    manifest = client.generate_scene_manifest(doc_text, title_hint)
    errors = _validate_manifest(manifest)
    if errors:
        log.warning("Legacy manifest validation issues; attempting repair: %s", errors[:3])
        manifest = _repair_manifest(manifest)
        errors = _validate_manifest(manifest)
    if errors:
        log.warning("Legacy manifest still invalid after repair; retrying once")
        manifest = client.generate_scene_manifest(doc_text, title_hint)
        manifest = _repair_manifest(manifest)
        errors = _validate_manifest(manifest)
    if errors:
        raise RuntimeError(
            "Legacy scene manifest failed validation after repair + retry: "
            + "; ".join(errors)
        )
    return manifest


def _pdf_hash(title_hint: str, doc_text: str) -> str:
    """Stable cache key for a document."""
    import hashlib
    h = hashlib.sha256()
    h.update((title_hint or "").encode("utf-8"))
    h.update(b"\0")
    h.update(doc_text.encode("utf-8"))
    return h.hexdigest()[:16]


def save_manifest(manifest: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    out_path = out_path or (CONFIG.output_dir / "scene_manifest.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    log.info("Wrote %s", out_path)
    return out_path


def load_manifest(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = path or (CONFIG.output_dir / "scene_manifest.json")
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
