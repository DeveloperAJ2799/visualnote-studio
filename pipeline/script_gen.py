"""Scene manifest generation.

Sends the full document text to a MiMoClient, validates the returned JSON
against the PRD §8 schema, and saves the result to `output/scene_manifest.json`.

A small in-place repair pass is applied if the LLM returns shapes that are
close-but-not-exact (e.g. `visual_type: mixed` for scenes that should clearly
be `manim_animation`). For more serious malformedness, a single retry is
attempted.
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
        if not isinstance(dur, int) or dur <= 0:
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
        if not isinstance(scene.get("duration_hint_s"), int) or scene["duration_hint_s"] <= 0:
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
) -> Dict[str, Any]:
    """Run scene manifest generation. Repairs and validates the response.

    Raises RuntimeError if validation still fails after repair + one retry.
    """
    doc_text = _build_doc_text(doc_content)
    title_hint = doc_content.get("document_title", "Untitled Document")

    log.info("Generating scene manifest (text length=%d)", len(doc_text))
    manifest = client.generate_scene_manifest(doc_text, title_hint)

    errors = _validate_manifest(manifest)
    if errors:
        log.warning("Manifest validation issues; attempting repair: %s", errors[:3])
        manifest = _repair_manifest(manifest)
        errors = _validate_manifest(manifest)
    if errors:
        log.warning("Manifest still invalid after repair; retrying once")
        # Caller can implement a retry by passing a different client; here we
        # simply re-issue the call once and accept whatever we get.
        manifest = client.generate_scene_manifest(doc_text, title_hint)
        manifest = _repair_manifest(manifest)
        errors = _validate_manifest(manifest)
    if errors:
        raise RuntimeError(
            "Scene manifest failed validation after repair + retry: "
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
