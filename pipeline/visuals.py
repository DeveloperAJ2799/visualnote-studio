"""Visual orchestrator — routes scenes to the appropriate renderer.

For each scene in the manifest, based on visual_type:
  - image_overlay: match PDF image, compose with Pillow → PNG
  - title_card: pure Pillow title card → PNG
  - html_frame: render HTML via Playwright → PNG (needs LLM client)
  - manim_animation: generate Manim code → MP4 (needs LLM client)
  - AI-generated images via Qwen Image (NVIDIA NIM) for manim/html scenes

When no LLM client is available (e.g. --skip-llm), html_frame and
manim_animation scenes use Qwen Image API or fall back to Pillow title cards.

All outputs are saved to output/scenes/scene_{NNN}.png or .mp4.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from config import CONFIG

log = logging.getLogger(__name__)


def render_visuals(
    manifest: dict,
    doc_content: Dict[str, Any],
    client: Optional[Any] = None,
    force: bool = False,
) -> list[Path]:
    """Render all scene visuals. Returns list of output paths.

    Args:
        manifest: The scene manifest with visual_type per scene.
        doc_content: Parsed PDF content with image_index for matching.
        client: Optional LLM client for html_frame and manim_animation.
                When None, those types fall back to Qwen Image or title cards.
        force: When True, re-render even if output files exist.

    Returns:
        Exactly one path per scene. Every scene always appends exactly one
        entry to the output list — even the final Pillow fallback is
        guaranteed to produce a file.
    """
    from pipeline.image_fetcher import render_image_overlay, render_title_card

    scenes = manifest.get("scenes", [])
    outputs: list[Path] = []

    # The HTML Canvas diagram generator is the preferred fast path for
    # html_frame / manim_animation scenes (no LLM needed).  Enabled by
    # default; the generator degrades gracefully to Pillow on failure.
    use_diagrams = True
    log.info("Using HTML Canvas diagram generator for visuals")

    for scene in scenes:
        scene_id = scene.get("scene_id", 0)
        visual_type = scene.get("visual_type", "title_card")
        out_path = CONFIG.scenes_dir / f"scene_{scene_id:03d}.png"

        # Skip if already rendered (unless force)
        if not force and out_path.exists():
            log.info("Scene %d: already rendered, skipping", scene_id)
            outputs.append(out_path)
            continue

        # Also check for .mp4 (manim output)
        out_mp4 = CONFIG.scenes_dir / f"scene_{scene_id:03d}.mp4"
        if not force and out_mp4.exists():
            log.info("Scene %d: already rendered (mp4), skipping", scene_id)
            outputs.append(out_mp4)
            continue

        # Track the rendered path so we always append exactly one entry.
        rendered: Optional[Path] = None

        try:
            if visual_type == "image_overlay":
                rendered = render_image_overlay(scene, doc_content)

            elif visual_type == "title_card":
                rendered = render_title_card(scene)

            elif visual_type in ("html_frame", "manim_animation"):
                rendered = _render_complex_scene(
                    scene, scene_id, visual_type, client,
                    use_diagrams=use_diagrams,
                )

            else:
                log.info("Scene %d: unknown type '%s', using title card",
                         scene_id, visual_type)
                rendered = render_title_card(scene)

        except Exception as exc:
            log.warning("Scene %d visual render failed (%s); using title card",
                        scene_id, exc)

        # Last-resort: if nothing was produced, force a title card.
        if rendered is None:
            try:
                rendered = render_title_card(scene)
            except Exception as exc2:
                # Absolute final fallback: create a 1x1 placeholder so the
                # scene index is never missing from the assembly.
                log.error(
                    "Scene %d: title card fallback also failed (%s); "
                    "writing placeholder",
                    scene_id, exc2,
                )
                _write_placeholder(out_path)
                rendered = out_path

        outputs.append(rendered)

    return outputs


def _render_complex_scene(
    scene: dict,
    scene_id: int,
    visual_type: str,
    client: Optional[Any],
    *,
    use_diagrams: bool,
) -> Optional[Path]:
    """Render an html_frame or manim_animation scene.

    Tries (in order):
      1. HTML Canvas diagram generator (if enabled)
      2. LLM-based renderer (Playwright or Manim)
      3. Pillow title card
    """
    from pipeline.image_fetcher import render_title_card

    # Try the diagram generator first (fast, no LLM needed) — but only
    # when the scene does NOT carry usable html_content.  The chairman
    # (or scriptwriter) may have generated HTML that is more faithful to
    # the narration than a generic concept-map would be.
    has_html = (
        isinstance(scene.get("html_content"), str)
        and len(scene["html_content"].strip()) > 40
    )
    if use_diagrams and not has_html:
        from pipeline.diagram_gen import generate_scene_diagram
        gen_path = CONFIG.scenes_dir / f"scene_{scene_id:03d}_diagram.png"
        result = generate_scene_diagram(scene, gen_path)
        if result is not None:
            return result

    # Try LLM-based renderer if available.
    if client is not None:
        if visual_type == "html_frame":
            from pipeline.html_gen import render_html_frame
            return render_html_frame(scene, client)
        elif visual_type == "manim_animation":
            from pipeline.manim_gen import render_manim_scene
            return render_manim_scene(scene, client)

    # Final fallback: title card.
    log.info(
        "Scene %d: %s without LLM/diagram, using title card",
        scene_id, visual_type,
    )
    return render_title_card(scene)


def _write_placeholder(path: Path) -> None:
    """Write a minimal 1x1 PNG so the scene index is never missing."""
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1, 1), "#000000").save(path, "PNG")
