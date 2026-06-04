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
    """
    from pipeline.image_fetcher import render_image_overlay, render_title_card

    scenes = manifest.get("scenes", [])
    outputs: list[Path] = []

    # Use diagram generator for AI visuals (manim/html scenes)
    use_diagrams = True
    if use_diagrams:
        from pipeline.diagram_gen import generate_scene_diagram
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

        try:
            if visual_type == "image_overlay":
                path = render_image_overlay(scene, doc_content)
                outputs.append(path)

            elif visual_type == "title_card":
                path = render_title_card(scene)
                outputs.append(path)

            elif visual_type in ("html_frame", "manim_animation"):
                # Generate HTML Canvas diagram for these scene types
                if use_diagrams:
                    gen_path = CONFIG.scenes_dir / f"scene_{scene_id:03d}_diagram.png"
                    result = generate_scene_diagram(scene, gen_path)
                    if result:
                        outputs.append(result)
                        continue

                # Fall back to LLM-based renderers if client available
                if client is not None:
                    if visual_type == "html_frame":
                        from pipeline.html_gen import render_html_frame
                        path = render_html_frame(scene, client)
                        outputs.append(path)
                    elif visual_type == "manim_animation":
                        from pipeline.manim_gen import render_manim_scene
                        path = render_manim_scene(scene, client)
                        outputs.append(path)
                else:
                    # Final fallback: title card
                    log.info("Scene %d: %s without LLM/Qwen, using title card",
                             scene_id, visual_type)
                    path = render_title_card(scene)
                    outputs.append(path)

            else:
                # Fallback: title card
                log.info("Scene %d: unknown type '%s', using title card",
                         scene_id, visual_type)
                path = render_title_card(scene)
                outputs.append(path)

        except Exception as exc:
            log.warning("Scene %d visual render failed (%s); using title card",
                        scene_id, exc)
            try:
                path = render_title_card(scene)
                outputs.append(path)
            except Exception as exc2:
                log.error("Scene %d: title card fallback also failed: %s",
                          scene_id, exc2)

    return outputs
