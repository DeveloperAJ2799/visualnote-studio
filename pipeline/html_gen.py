"""HTML frame rendering via Playwright (with Pillow fallback).

For each scene with `visual_type: html_frame`:
  1. Resolve the HTML body: call the LLM if the scene's html_content is a short
     hint, otherwise wrap the existing HTML string.
  2. Wrap the body in a minimal full-page document and load it in headless
     Chromium at 1920x1080.
  3. Screenshot full page → PNG at `output/scenes/scene_{id}.png`.

If Playwright fails for any reason, a Pillow-rendered title card is produced
as a graceful fallback.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from config import CONFIG
from pipeline.clients.base import MiMoClient
from pipeline.manim_gen import _make_title_card_png

log = logging.getLogger(__name__)

DEFAULT_VIEWPORT: Tuple[int, int] = (1920, 1080)

_HTML_DOC_TEMPLATE = """\
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0;
    padding: 0;
    background: #1a1a2e;
    color: #f0f0f0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    overflow: hidden;
  }}
  body {{
    width: {w}px;
    height: {h}px;
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _looks_like_html(s: str) -> bool:
    """Heuristic: does the string look like a full HTML body, or just a hint?"""
    if not s:
        return False
    lowered = s.strip().lower()
    if lowered.startswith(("<div", "<section", "<h1", "<h2", "<p", "<span", "<svg", "<table")):
        return True
    if "<" in s and ">" in s and len(s) > 80:
        return True
    return False


def _resolve_html_body(
    scene: dict,
    client: MiMoClient,
) -> str:
    """Return an HTML body fragment for the scene."""
    raw = scene.get("html_content")
    if isinstance(raw, str) and _looks_like_html(raw):
        return raw
    hint = raw if isinstance(raw, str) and raw.strip() else "definition"
    title = scene.get("title", "Scene")
    narration = scene.get("narration", "")
    return client.generate_html_frame(title, narration, hint)


def _wrap_doc(body_html: str, viewport: Tuple[int, int]) -> str:
    w, h = viewport
    return _HTML_DOC_TEMPLATE.format(body=body_html, w=w, h=h)


def _render_with_playwright(
    html: str,
    out_path: Path,
    viewport: Tuple[int, int] = DEFAULT_VIEWPORT,
) -> bool:
    """Render the HTML to a PNG via headless Chromium. Returns True on success."""
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(150)
            page.screenshot(path=str(out_path), full_page=False)
        finally:
            browser.close()
    return out_path.exists() and out_path.stat().st_size > 0


def render_html_frame(
    scene: dict,
    client: MiMoClient,
    *,
    viewport: Tuple[int, int] = DEFAULT_VIEWPORT,
) -> Path:
    """Render a single html_frame scene. Returns path to a PNG."""
    scene_id = scene["scene_id"]
    out_png = CONFIG.scenes_dir / f"scene_{scene_id:03d}.png"
    frame_html_path = CONFIG.frames_dir / f"scene_{scene_id:03d}.html"

    if out_png.exists():
        log.info("Scene %d html frame already rendered: %s", scene_id, out_png)
        return out_png

    try:
        body = _resolve_html_body(scene, client)
        full_html = _wrap_doc(body, viewport)
        try:
            frame_html_path.write_text(full_html, encoding="utf-8")
        except OSError as exc:
            log.warning("Failed to write frame html: %s", exc)
        if _render_with_playwright(full_html, out_png, viewport):
            log.info("Scene %d html frame rendered: %s", scene_id, out_png)
            return out_png
    except Exception as exc:
        log.warning("Playwright render failed for scene %d: %s", scene_id, exc)

    log.error("Scene %d: falling back to title card", scene_id)
    return _make_title_card_png(
        scene.get("title", "Scene"),
        scene.get("narration", "")[:200],
        out_png,
        size=viewport,
    )


def render_html_frames(manifest: dict, client: MiMoClient) -> list[Path]:
    """Render every html_frame scene in the manifest."""
    paths: list[Path] = []
    for scene in manifest.get("scenes", []):
        if scene.get("visual_type") != "html_frame":
            continue
        paths.append(render_html_frame(scene, client))
    return paths
