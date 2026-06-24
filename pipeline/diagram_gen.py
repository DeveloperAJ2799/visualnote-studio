"""Diagram generator using HTML Canvas + Playwright screenshots.

Since Qwen Image requires a local Docker container, we generate
educational diagrams using styled HTML rendered via Playwright.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

from config import CONFIG

log = logging.getLogger(__name__)


def generate_scene_diagram(
    scene: dict,
    out_path: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    browser=None,
) -> Optional[Path]:
    """Generate an educational diagram for a scene using HTML Canvas.

    Args:
        scene: Scene dict with title, narration, visual_type, etc.
        out_path: Where to save the generated PNG.
        width: Output image width.
        height: Output image height.
        browser: Optional Playwright browser instance to reuse.

    Returns:
        Path to saved image, or None on failure.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        return out_path

    scene_id = scene.get("scene_id", 0)
    title = scene.get("title", "Scene")
    narration = scene.get("narration", "")[:300]
    visual_type = scene.get("visual_type", "diagram")

    # Generate themed HTML diagram
    html = _build_diagram_html(title, narration, visual_type, width, height)

    # Try Playwright first, fall back to Pillow
    _owned_browser = False
    _pw = None
    try:
        from playwright.sync_api import sync_playwright
        if browser is None:
            _pw = sync_playwright().start()
            browser = _pw.chromium.launch(headless=True)
            _owned_browser = True
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=str(out_path), full_page=False)
        page.close()
        log.info("Scene %d: diagram rendered via Playwright to %s", scene_id, out_path)
        return out_path
    except Exception as exc:
        log.warning("Scene %d: Playwright failed (%s), trying Pillow", scene_id, exc)
    finally:
        if _owned_browser:
            browser.close()
            if _pw:
                _pw.stop()

    # Pillow fallback
    try:
        _render_diagram_pillow(title, narration, visual_type, out_path, width, height)
        log.info("Scene %d: diagram rendered via Pillow to %s", scene_id, out_path)
        return out_path
    except Exception as exc2:
        log.error("Scene %d: Pillow fallback also failed: %s", scene_id, exc2)
        return None


def _build_diagram_html(
    title: str,
    narration: str,
    visual_type: str,
    width: int,
    height: int,
) -> str:
    """Build styled HTML for an educational diagram."""
    # Color themes based on visual type
    themes = {
        "manim_animation": {"primary": "#e94560", "secondary": "#4fc3f7", "bg": "#0a0e27"},
        "html_frame": {"primary": "#7c4dff", "secondary": "#f5a623", "bg": "#1a1a2e"},
        "default": {"primary": "#4fc3f7", "secondary": "#e94560", "bg": "#16213e"},
    }
    theme = themes.get(visual_type, themes["default"])

    # Extract key concepts from narration for diagram labels
    keywords = _extract_keywords(narration)
    labels_html = ""
    for i, kw in enumerate(keywords[:6]):
        angle = i * 60
        labels_html += f'''
        <div class="concept-node" style="
            transform: rotate({angle}deg) translateY(-180px) rotate(-{angle}deg);
            background: {theme['primary'] if i % 2 == 0 else theme['secondary']};
        ">{kw}</div>
        '''

    return f'''<!DOCTYPE html>
<html>
<head>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        width: {width}px; height: {height}px;
        background: {theme['bg']};
        font-family: 'Segoe UI', system-ui, sans-serif;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    .diagram {{
        position: relative;
        width: 800px; height: 800px;
    }}
    .center-title {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        width: 200px; height: 200px;
        background: {theme['bg']};
        border: 3px solid {theme['primary']};
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: white;
        font-size: 18px;
        font-weight: 700;
        padding: 20px;
        z-index: 10;
        box-shadow: 0 0 40px {theme['primary']}40;
    }}
    .concept-node {{
        position: absolute;
        top: 50%; left: 50%;
        width: 140px; height: 50px;
        margin: -25px 0 0 -70px;
        border-radius: 25px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 14px;
        font-weight: 600;
        text-align: center;
        padding: 8px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }}
    .connector {{
        position: absolute;
        top: 50%; left: 50%;
        width: 160px; height: 2px;
        background: linear-gradient(90deg, {theme['primary']}, {theme['secondary']});
        transform-origin: left center;
        opacity: 0.6;
    }}
    .bg-circle {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        border: 1px solid {theme['primary']}30;
        border-radius: 50%;
    }}
    .bg-circle.c1 {{ width: 400px; height: 400px; }}
    .bg-circle.c2 {{ width: 550px; height: 550px; border-color: {theme['secondary']}20; }}
    .bg-circle.c3 {{ width: 700px; height: 700px; border-color: {theme['primary']}10; }}
</style>
</head>
<body>
    <div class="diagram">
        <div class="bg-circle c1"></div>
        <div class="bg-circle c2"></div>
        <div class="bg-circle c3"></div>
        <div class="center-title">{title[:40]}</div>
        {labels_html}
    </div>
</body>
</html>'''


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from narration text."""
    # Common educational terms to highlight
    edu_terms = [
        "cell", "nucleus", "membrane", "protein", "DNA", "RNA",
        "mitochondria", "ribosome", "enzyme", "ATP", "glucose",
        "phospholipid", "bilayer", "organelle", "cytoplasm",
        "ribosome", "endoplasmic", "reticulum", "Golgi", "lysosome",
        "chloroplast", "photosynthesis", "respiration", "metabolism",
        "amino", "acid", "fatty", "lipid", "carbohydrate",
        "bacteria", "archaea", "eukaryote", "prokaryote",
        "transcription", "translation", "replication",
        "hydrogen", "bond", "covalent", "ionic",
        "osmosis", "diffusion", "transport", "channel",
        "receptor", "signal", "pathway", "gene",
    ]

    words = text.lower().split()
    found = []
    for term in edu_terms:
        if term.lower() in text.lower() and term not in found:
            found.append(term.capitalize())
            if len(found) >= 6:
                break

    # If not enough keywords found, extract capitalized words
    if len(found) < 3:
        for word in words:
            cleaned = word.strip(".,;:()[]{}!?")
            if len(cleaned) > 4 and cleaned[0].isupper() and cleaned not in found:
                found.append(cleaned)
                if len(found) >= 6:
                    break

    return found if found else ["Concept", "Process", "Structure", "Function"]


def _render_diagram_pillow(
    title: str,
    narration: str,
    visual_type: str,
    out_path: Path,
    width: int,
    height: int,
) -> None:
    """Render a diagram using Pillow as fallback."""
    from PIL import Image, ImageDraw, ImageFont

    # Color scheme
    bg_color = "#0a0e27"
    primary = "#e94560"
    secondary = "#4fc3f7"

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Draw concentric circles
    cx, cy = width // 2, height // 2
    for r in [350, 275, 200]:
        color = primary if r == 275 else secondary
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=color, width=2)

    # Draw center circle with title
    draw.ellipse([cx-120, cy-120, cx+120, cy+120], fill=bg_color, outline=primary, width=3)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
        small_font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
        small_font = font

    # Center text
    words = title.split()
    line1 = " ".join(words[:2])
    line2 = " ".join(words[2:4]) if len(words) > 2 else ""
    bbox1 = draw.textbbox((0, 0), line1, font=font)
    draw.text((cx - (bbox1[2]-bbox1[0])//2, cy - 20), line1, fill="white", font=font)
    if line2:
        bbox2 = draw.textbbox((0, 0), line2, font=font)
        draw.text((cx - (bbox2[2]-bbox2[0])//2, cy + 10), line2, fill="white", font=font)

    # Draw concept nodes around the center
    keywords = _extract_keywords(narration)
    for i, kw in enumerate(keywords[:6]):
        angle = math.radians(i * 60 - 90)
        nx = cx + int(220 * math.cos(angle))
        ny = cy + int(220 * math.sin(angle))

        # Node box
        bbox = draw.textbbox((0, 0), kw, font=small_font)
        tw = bbox[2] - bbox[0]
        draw.rounded_rectangle(
            [nx - tw//2 - 15, ny - 15, nx + tw//2 + 15, ny + 15],
            radius=15,
            fill=primary if i % 2 == 0 else secondary,
        )
        draw.text((nx - tw//2, ny - 8), kw, fill="white", font=small_font)

        # Connector line
        draw.line([cx, cy, nx, ny], fill=primary, width=2)

    img.save(str(out_path), "PNG")


__all__ = ["generate_scene_diagram"]
