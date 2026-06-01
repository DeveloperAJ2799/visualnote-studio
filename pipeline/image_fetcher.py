"""Image fetch + composition for scenes with visual_type image_overlay or title_card.

Phase 1 (MVP) implementation:
  1. PDF asset lookup by token overlap with the scene's title + narration.
  2. Pillow resize + blurred background padding to 1920x1080.
  3. Pure Pillow title-card fallback when no match is found or no image is wanted.

The image source chain is structured so a Phase 2 addition (Unsplash or
Wikimedia fetch) slots in between step 1 and step 2 without changing the rest
of the pipeline. See `_resolve_image()` below.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageFilter

from config import CONFIG
from pipeline.manim_gen import _make_title_card_png

log = logging.getLogger(__name__)

DEFAULT_SIZE: Tuple[int, int] = (1920, 1080)
GAUSSIAN_RADIUS = 24


def _score_image_against_text(
    image_keywords: List[str],
    query_tokens: set,
) -> int:
    """Return the number of overlapping tokens (case-insensitive)."""
    if not image_keywords or not query_tokens:
        return 0
    img_tokens = {k.lower() for k in image_keywords}
    return len(img_tokens & query_tokens)


def _pick_best_image(
    image_index: List[Dict[str, Any]],
    query_text: str,
) -> Optional[Dict[str, Any]]:
    """Pick the highest-scoring image for the query, or None if no overlap."""
    query_tokens = {
        t.lower() for t in query_text.split() if len(t) > 2
    }
    if not query_tokens:
        return None
    best: Optional[Dict[str, Any]] = None
    best_score = 0
    for img in image_index:
        kw = img.get("keywords") or []
        score = _score_image_against_text(kw, query_tokens)
        if score > best_score:
            best_score = score
            best = img
    return best if best_score > 0 else None


def _resolve_image(scene: dict, doc_content: Dict[str, Any]) -> Optional[Path]:
    """Return the path to a suitable image for the scene, or None.

    Phase 1 only consults the PDF asset index. Phase 2 will add Unsplash and
    Wikimedia lookups between the PDF check and the return.
    """
    image_index = doc_content.get("image_index") or []
    if not image_index:
        return None
    query = f"{scene.get('title','')} {scene.get('narration','')}"
    match = _pick_best_image(image_index, query)
    if not match:
        return None
    p = Path(match.get("abs_path") or (CONFIG.project_root / match["path"]))
    return p if p.exists() else None


def _compose_blurred(
    image_path: Path,
    out_path: Path,
    size: Tuple[int, int] = DEFAULT_SIZE,
) -> Path:
    """Resize `image_path` to `size` with blurred background padding."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as src:
        src = src.convert("RGB")
        sw, sh = src.size
        target_w, target_h = size
        # Scale source to fill (cover) the canvas, then blur the upscaled copy
        # and paste the original on top, centered, with aspect preserved.
        scale = max(target_w / sw, target_h / sh)
        bg_w, bg_h = int(sw * scale), int(sh * scale)
        bg = src.resize((bg_w, bg_h), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=GAUSSIAN_RADIUS))
        # Crop to canvas
        left = (bg_w - target_w) // 2
        top = (bg_h - target_h) // 2
        bg = bg.crop((left, top, left + target_w, top + target_h))
        # Foreground: fit-inside the canvas with a small inset for breathing room
        inset = int(min(target_w, target_h) * 0.05)
        max_fg_w = target_w - 2 * inset
        max_fg_h = target_h - 2 * inset
        fg_scale = min(max_fg_w / sw, max_fg_h / sh, 1.0)
        if fg_scale < 1.0:
            fg = src.resize(
                (max(1, int(sw * fg_scale)), max(1, int(sh * fg_scale))),
                Image.LANCZOS,
            )
        else:
            fg = src
        fx = (target_w - fg.size[0]) // 2
        fy = (target_h - fg.size[1]) // 2
        bg.paste(fg, (fx, fy))
        bg.save(out_path, "PNG", optimize=True)
    return out_path


def render_image_overlay(
    scene: dict,
    doc_content: Dict[str, Any],
) -> Path:
    """Render a single image_overlay scene. Returns a PNG path."""
    scene_id = scene["scene_id"]
    out_png = CONFIG.scenes_dir / f"scene_{scene_id:03d}.png"

    if out_png.exists():
        log.info("Scene %d image overlay already rendered: %s", scene_id, out_png)
        return out_png

    image_path = _resolve_image(scene, doc_content)
    if image_path:
        try:
            return _compose_blurred(image_path, out_png)
        except Exception as exc:
            log.warning("Image composition failed for scene %d: %s", scene_id, exc)
    log.info("Scene %d: no image match; using title-card fallback", scene_id)
    return _make_title_card_png(
        scene.get("title", "Scene"),
        scene.get("narration", "")[:200],
        out_png,
    )


def render_title_card(scene: dict) -> Path:
    """Render a pure-Pillow title card."""
    scene_id = scene["scene_id"]
    out_png = CONFIG.scenes_dir / f"scene_{scene_id:03d}.png"
    if out_png.exists():
        log.info("Scene %d title card already rendered: %s", scene_id, out_png)
        return out_png
    return _make_title_card_png(
        scene.get("title", "Scene"),
        scene.get("narration", "")[:200],
        out_png,
    )


def render_image_overlays(manifest: dict, doc_content: Dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for scene in manifest.get("scenes", []):
        vt = scene.get("visual_type")
        if vt == "image_overlay":
            paths.append(render_image_overlay(scene, doc_content))
        elif vt == "title_card":
            paths.append(render_title_card(scene))
    return paths
