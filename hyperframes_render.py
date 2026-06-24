"""HyperFrames-based video assembler.

Replaces the moviepy-based assembler (pipeline/assembler.py) with a single
HyperFrames HTML composition. Each scene in the manifest becomes a timed
composition segment with:
  - GSAP-animated title card / panel / image overlay
  - Per-scene TTS audio as an <audio> track
  - Shader-based transitions between scenes
  - Motion graphics (Ken Burns, particle backgrounds, animated text)

The composition is rendered to MP4 by invoking the `hyperframes` CLI via
subprocess. This module follows the official HyperFrames engine contract:

  * Composition root: first element with data-width + data-height.
  * Timed clips must have class="clip" so the engine manages their
    visibility lifecycle. The engine handles per-clip opacity from
    data-start / data-duration automatically.
  * Animations: register a paused GSAP timeline on
    `window.__timelines["<composition-id>"]`. The engine seeks it.
  * Audio: native <audio data-track-index> so the engine handles mux.

Usage:
    from hyperframes_render import render_with_hyperframes
    render_with_hyperframes(manifest, output_path)
"""
from __future__ import annotations

import json
import logging
import math
import re
import shutil
import subprocess
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import CONFIG
from pipeline.tts import _probe_wav_duration

log = logging.getLogger(__name__)

WIDTH = 1920
HEIGHT = 1080
FPS = 24
CROSSFADE_S = 0.3
COMPOSITION_ID = "visualnote-deep"

# Mapping from frame_style (used in manifest) → CSS class suffix (used in HTML).
# Names must match the .layout-* CSS rules below.
_FRAME_STYLE_TO_LAYOUT = {
    "title_hero": "centered",
    "text_only": "centered",
    "quote_callout": "centered",
    "chapter_marker": "chapter-marker",
    "image_left": "default",
    "image_right": "image-right",
    "diagram_center": "default",
    "split_compare": "default",
    "listing_columns": "listing",
    "full_bleed": "full-bleed",
    "steps_horizontal": "steps-horizontal",
    "stats_grid": "stats-grid",
    "type_columns": "type-columns",
    "flow_chain": "flow-chain",
    "process_flow": "process-flow",
    "infographic": "infographic",
    "venn_diagram": "venn-diagram",
    "pyramid": "pyramid",
    "cycle_diagram": "cycle-diagram",
    "funnel": "funnel",
    "flowchart": "flowchart",
    "pie_chart": "pie-chart",
    "bar_chart": "bar-chart",
    "annotated_diagram": "annotated-diagram",
}

PALETTE = {
    "bg_dark": "#0a0e27",
    "bg_mid": "#16213e",
    "bg_light": "#1a1a2e",
    "accent": "#e94560",
    "accent2": "#4fc3f7",
    "accent3": "#f5a623",
    "accent4": "#7c4dff",
    "text": "#f0f0f0",
    "text_dim": "#9aa0b4",
    "good": "#4caf50",
    "panel_bg": "rgba(15, 52, 96, 0.85)",
}


# ---------------------------------------------------------------------------
# Asset resolution
# ---------------------------------------------------------------------------


def _to_asset_url(target: Path, base: Path) -> str:
    """Return a relative posix path if `target` is inside `base`, else an
    absolute OS path.  The engine's audio/video mixers call ``existsSync``
    on the ``src`` attribute — ``file://`` URLs fail that check, so we
    always return a raw filesystem path here.
    """
    try:
        rel = Path(target).resolve().relative_to(Path(base).resolve())
        return rel.as_posix()
    except ValueError:
        return str(Path(target).resolve())


def _to_audio_src(audio_path: Path) -> str:
    """Return an absolute OS path for an audio file.

    The engine's audio mixer resolves ``<audio src>`` via Node's
    ``fs.existsSync`` — ``file://`` URLs and relative paths that escape
    the project directory both fail that check.  Absolute paths work
    everywhere.
    """
    return str(Path(audio_path).resolve())


def _html_escape(s: str) -> str:
    return escape(s, quote=True)


def _parse_listing_items(narration: str) -> list:
    """Parse narration text into listing items (title + description pairs)."""
    items = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Handle numbered items: "1. Item description"
        if line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                items.append({"title": parts[0] + ".", "desc": parts[1]})
                continue
        # Handle bullet points: "- Item" or "* Item"
        if line.startswith(("- ", "* ")):
            items.append({"title": "", "desc": line[2:]})
            continue
        # Handle colon-separated: "Title: Description"
        if ": " in line:
            parts = line.split(": ", 1)
            if len(parts) == 2 and len(parts[0]) < 50:
                items.append({"title": parts[0], "desc": parts[1]})
                continue
        # Default: treat whole line as a description
        items.append({"title": "", "desc": line})
    # Limit to 6 items for 3-column layout
    return items[:6]


def _parse_steps(narration: str) -> list:
    """Parse narration text into numbered steps."""
    steps = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Handle numbered items: "1. Step description"
        if line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                steps.append(parts[1])
                continue
        # Handle bullet points
        if line.startswith(("- ", "* ")):
            steps.append(line[2:])
            continue
        # Default: treat as a step
        steps.append(line)
    # Limit to 5 steps
    return steps[:5]


def _parse_stats(narration: str) -> list:
    """Parse narration text into stat cards (value + label pairs)."""
    stats = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Handle patterns like "70% of ..." or "3.5 billion ..."
        # Look for number at start
        match = re.match(r'^([\d.,]+[%xBx]?)\s*[-–—:]\s*(.+)', line)
        if match:
            stats.append({"value": match.group(1), "label": match.group(2)})
            continue
        # Handle "X: Y" format
        if ": " in line:
            parts = line.split(": ", 1)
            if len(parts) == 2 and any(c.isdigit() for c in parts[0]):
                stats.append({"value": parts[0], "label": parts[1]})
                continue
    # Default stats if parsing fails
    if not stats:
        stats = [
            {"value": "4", "label": "Core Elements"},
            {"value": "4", "label": "Macromolecules"},
            {"value": "~37T", "label": "Cells in Body"},
            {"value": "100%", "label": "Carbon-Based"},
        ]
    return stats[:4]


def _parse_type_items(narration: str) -> list:
    """Parse narration text into type items for type_columns layout.

    Handles patterns like:
    - "Primary proteins: ..."
    - "1. Monosaccharides: ..."
    - "- Simple carbs: ..."
    - "Type A - description"
    """
    items = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Handle numbered items: "1. Type: description"
        if line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                # Split on first colon for title:desc
                sub_parts = parts[1].split(": ", 1)
                if len(sub_parts) == 2:
                    items.append({"title": sub_parts[0], "desc": sub_parts[1]})
                else:
                    items.append({"title": sub_parts[0], "desc": ""})
                continue
        # Handle bullet points: "- Type: description"
        if line.startswith(("- ", "* ")):
            sub_parts = line[2:].split(": ", 1)
            if len(sub_parts) == 2:
                items.append({"title": sub_parts[0], "desc": sub_parts[1]})
            else:
                items.append({"title": sub_parts[0], "desc": ""})
            continue
        # Handle "Type - description" or "Type: description"
        if " - " in line:
            parts = line.split(" - ", 1)
            if len(parts) == 2 and len(parts[0]) < 60:
                items.append({"title": parts[0], "desc": parts[1]})
                continue
        if ": " in line:
            parts = line.split(": ", 1)
            if len(parts) == 2 and len(parts[0]) < 60:
                items.append({"title": parts[0], "desc": parts[1]})
                continue
    # Default items if parsing fails
    if not items:
        items = [
            {"title": "Type A", "desc": "First category"},
            {"title": "Type B", "desc": "Second category"},
            {"title": "Type C", "desc": "Third category"},
        ]
    return items[:6]


def _parse_flow_steps(narration: str) -> list:
    """Parse narration text into flow steps for flow_chain/process_flow layouts.

    Handles patterns like:
    - "1. Step description"
    - "First, ..."
    - "Then ..."
    - "Finally, ..."
    - "Step 1: description"
    - Sentences connected by arrows or "→"
    """
    steps = []

    # First try to find explicit steps (numbered or bullet)
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                steps.append(parts[1])
                continue
        if line.startswith(("- ", "* ")):
            steps.append(line[2:])
            continue
        if line.lower().startswith(("step ", "stage ")):
            parts = line.split(": ", 1)
            if len(parts) == 2:
                steps.append(parts[1])
                continue

    # If no explicit steps, try to extract from sequential language
    if not steps:
        # Look for "first", "then", "next", "finally" patterns
        seq_pattern = re.compile(
            r'(?:first|then|next|after that|finally|subsequently|'
            r'as a result|this leads to|which produces?|resulting in)\s+',
            re.IGNORECASE
        )
        parts = seq_pattern.split(narration)
        for part in parts:
            part = part.strip().strip(',').strip('.')
            if part and len(part) > 10:
                steps.append(part)

    # If still no steps, split by sentences and take first few
    if not steps:
        sentences = re.split(r'(?<=[.!?])\s+', narration)
        steps = [s.strip() for s in sentences if len(s.strip()) > 10][:5]

    return steps[:6]


def _parse_venn_items(narration: str) -> list:
    """Parse narration into Venn diagram sets (2-3 overlapping groups)."""
    items = []
    parts = re.split(r'[;\n]', narration)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            name_part, items_part = part.split(':', 1)
            name_part = name_part.strip()
            if len(name_part) < 40:
                items.append({"name": name_part, "values": items_part.strip()})
    if len(items) < 2:
        items = [
            {"name": "Set A", "values": "Properties unique to A"},
            {"name": "Set B", "values": "Properties unique to B"},
            {"name": "Shared", "values": "Common properties"},
        ]
    return items[:3]


def _parse_pyramid_items(narration: str) -> list:
    """Parse narration into pyramid levels (bottom to top)."""
    items = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'(?:Level\s+)?(\d+)[.:\s]+(.+)', line, re.IGNORECASE)
        if match:
            label = match.group(2).strip()
            if " - " in label:
                parts = label.split(" - ", 1)
                items.append({"label": parts[0], "desc": parts[1]})
            elif ": " in label:
                parts = label.split(": ", 1)
                items.append({"label": parts[0], "desc": parts[1]})
            else:
                items.append({"label": label, "desc": ""})
            continue
        if ": " in line:
            parts = line.split(": ", 1)
            if len(parts[0]) < 30:
                items.append({"label": parts[0], "desc": parts[1]})
    if len(items) < 3:
        items = [
            {"label": "Level 1", "desc": "Foundation level"},
            {"label": "Level 2", "desc": "Intermediate level"},
            {"label": "Level 3", "desc": "Advanced level"},
        ]
    return items[:5]


def _parse_cycle_items(narration: str) -> list:
    """Parse narration into cycle steps (circular process)."""
    items = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                items.append(parts[1])
                continue
        if line.startswith(("- ", "* ")):
            items.append(line[2:])
            continue
        if ": " in line:
            parts = line.split(": ", 1)
            if len(parts[0]) < 30:
                items.append(f"{parts[0]}: {parts[1]}")
                continue
        if len(line) > 10:
            items.append(line)
    if len(items) < 3:
        items = ["Phase 1", "Phase 2", "Phase 3", "Phase 4"]
    return items[:6]


def _parse_funnel_items(narration: str) -> list:
    """Parse narration into funnel stages (top to bottom, decreasing)."""
    items = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                items.append(parts[1])
                continue
        if ": " in line:
            parts = line.split(": ", 1)
            if len(parts[0]) < 30:
                items.append(f"{parts[0]}: {parts[1]}")
                continue
        if len(line) > 5:
            items.append(line)
    if len(items) < 3:
        items = ["All inputs", "Filtered selection", "Final output"]
    return items[:5]


def _parse_flowchart_items(narration: str) -> list:
    """Parse narration into flowchart nodes (decision + process)."""
    items = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(k in lower for k in ("if", "whether", "should", "is it", "can it")):
            items.append({"type": "decision", "label": line})
        elif any(k in lower for k in ("start", "begin", "initial")):
            items.append({"type": "start", "label": line})
        elif any(k in lower for k in ("end", "finish", "output", "result")):
            items.append({"type": "end", "label": line})
        elif line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                items.append({"type": "process", "label": parts[1]})
        elif line.startswith(("- ", "* ")):
            items.append({"type": "process", "label": line[2:]})
        else:
            items.append({"type": "process", "label": line})
    if len(items) < 3:
        items = [
            {"type": "start", "label": "Start"},
            {"type": "decision", "label": "Condition?"},
            {"type": "process", "label": "Process"},
            {"type": "end", "label": "End"},
        ]
    return items[:8]


def _parse_pie_data(narration: str) -> list:
    """Parse narration into pie chart slices (label + percentage)."""
    slices = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^(\d+(?:\.\d+)?)\s*%\s*[-–—:of]+\s*(.+)', line, re.IGNORECASE)
        if match:
            slices.append({"label": match.group(2).strip(), "percent": float(match.group(1))})
            continue
        match = re.match(r'^(.+?):\s*(\d+(?:\.\d+)?)\s*%$', line, re.IGNORECASE)
        if match:
            slices.append({"label": match.group(1).strip(), "percent": float(match.group(2))})
    if not slices:
        slices = [
            {"label": "Category A", "percent": 35},
            {"label": "Category B", "percent": 30},
            {"label": "Category C", "percent": 20},
            {"label": "Category D", "percent": 15},
        ]
    return slices[:6]


def _parse_bar_data(narration: str) -> list:
    """Parse narration into bar chart data (label + value)."""
    bars = []
    lines = narration.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^(.+?):\s*([\d.]+)', line)
        if match:
            bars.append({"label": match.group(1).strip(), "value": float(match.group(2))})
            continue
        match = re.match(r'^([\d.]+)\s*[-–—]\s*(.+)', line)
        if match:
            bars.append({"label": match.group(2).strip(), "value": float(match.group(1))})
    if not bars:
        bars = [
            {"label": "Item A", "value": 40},
            {"label": "Item B", "value": 30},
            {"label": "Item C", "value": 25},
            {"label": "Item D", "value": 20},
        ]
    return bars[:8]


def _parse_annotation_items(narration: str) -> list:
    """Parse narration into annotation labels (label + position hint)."""
    items = []
    positions = ["top", "right", "bottom", "left"]
    lines = narration.strip().split("\n")
    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if ": " in line:
            parts = line.split(": ", 1)
            if len(parts[0]) < 40:
                items.append({"label": parts[0], "desc": parts[1], "pos": positions[idx % 4]})
                continue
        if line and line[0].isdigit() and ". " in line[:5]:
            parts = line.split(". ", 1)
            if len(parts) == 2:
                items.append({"label": parts[1], "desc": "", "pos": positions[idx % 4]})
                continue
        if len(line) > 5:
            items.append({"label": line, "desc": "", "pos": positions[idx % 4]})
    if not items:
        items = [
            {"label": "Component A", "desc": "First part", "pos": "top"},
            {"label": "Component B", "desc": "Second part", "pos": "right"},
            {"label": "Component C", "desc": "Third part", "pos": "bottom"},
        ]
    return items[:6]


def _find_visual(scene: dict) -> Optional[Path]:
    scene_id = scene.get("scene_id")
    if scene_id is None:
        return None
    base = CONFIG.scenes_dir
    candidates = [
        base / f"scene_{scene_id:03d}{suffix}"
        for suffix in (".mp4", ".png", ".jpg", ".jpeg", ".webp")
    ] + [
        base / f"scene_{scene_id:03d}_diagram{suffix}"
        for suffix in (".png", ".jpg", ".jpeg", ".webp", ".mp4")
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _find_audio(scene: dict) -> Optional[Path]:
    scene_id = scene.get("scene_id")
    if scene_id is None:
        return None
    wav = CONFIG.scenes_dir / f"scene_{scene_id:03d}_audio.wav"
    if wav.exists():
        return wav
    return None


def _format_panel_subtitle(narration: str, max_len: int = 320) -> str:
    n = re.sub(r"\s+", " ", narration or "").strip()
    if len(n) <= max_len:
        return n
    return n[: max_len - 1].rstrip() + "\u2026"


def _scene_durations(scenes: List[dict]) -> List[float]:
    """Per-scene duration in seconds, based on TTS audio length if available."""
    out: List[float] = []
    for scene in scenes:
        audio = _find_audio(scene)
        dur = 0.0
        if audio:
            try:
                dur = _probe_wav_duration(audio)
            except Exception:
                dur = 0.0
        if dur <= 0:
            dur = float(scene.get("duration_hint_s") or 15)
        out.append(max(dur, 2.0))
    return out


def _scene_start_offsets(scenes: List[dict]) -> List[float]:
    durs = _scene_durations(scenes)
    starts: List[float] = []
    cursor = 0.0
    for d in durs:
        starts.append(cursor)
        cursor += d
    return starts


# ---------------------------------------------------------------------------
# Composition builder
# ---------------------------------------------------------------------------


def _build_composition_html(
    manifest: dict,
    project_root: Path,
) -> Tuple[str, float]:
    """Build a HyperFrames index.html for the manifest. Returns (html, total_duration).

    Follows the engine contract:
      * composition root: first element with data-width + data-height
      * every timed element has class="clip" so the engine manages opacity
      * a paused GSAP timeline is registered on window.__timelines
      * audio is <audio data-track-index> so the engine handles the mux
    """
    scenes = manifest.get("scenes", [])
    if not scenes:
        raise ValueError("Manifest has no scenes to render.")

    starts = _scene_start_offsets(scenes)
    durs = _scene_durations(scenes)
    total_duration = starts[-1] + durs[-1]

    # ---------- tracks ----------
    # track 0: persistent background (always visible, NOT a clip)
    # track 1: per-scene panel-wrap (one clip per scene, contains everything)
    # track 2: per-scene audio (sequential, engine handles mux)
    # track 3: per-scene transition flash
    # All clips on a given track must be sequential (no overlap) per the
    # engine's static guard — see the hyperframes "data-attributes" docs.
    # Keeping title/body/bg-image INSIDE panel-wrap (no class="clip") avoids
    # overlap conflicts while the engine still manages panel visibility.
    TRACK_BG = 0
    TRACK_PANEL = 1
    TRACK_AUDIO = 2
    TRACK_TRANS = 3

    layers: List[str] = []

    # Persistent background (visible the whole time, no class="clip" because
    # it has no data-start/duration; not a clip the engine tracks).
    layers.append('<div class="bg-gradient"></div>')
    layers.append(
        '<div class="chrome">'
        '  <div class="bg-orbs">'
        '    <div class="orb orb-a"></div>'
        '    <div class="orb orb-b"></div>'
        '    <div class="orb orb-c"></div>'
        '  </div>'
        '</div>'
    )

    # Per-scene panel + audio
    for i, (scene, start, dur) in enumerate(zip(scenes, starts, durs)):
        sid = scene.get("scene_id", i + 1)
        is_first = i == 0
        is_last = i == len(scenes) - 1
        title_text = _html_escape(scene.get("title") or "Scene")
        body_text = _html_escape(
            _format_panel_subtitle(scene.get("narration") or "")
        )
        visual = _find_visual(scene)
        has_image_bg = bool(
            visual and visual.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )
        has_video_bg = bool(visual and visual.suffix.lower() == ".mp4")

        # Determine frame style and layout class
        frame_style = scene.get("frame_style", "")
        # Safety net: if frame_style is empty, derive from visual_type
        if not frame_style:
            vt = scene.get("visual_type", "title_card")
            if vt == "title_card":
                frame_style = "title_hero" if is_first or is_last else "chapter_marker"
            elif vt == "html_frame":
                frame_style = "listing_columns"
            elif vt == "manim_animation":
                frame_style = "diagram_center"
            elif vt == "image_overlay":
                frame_style = "image_left"
            else:
                frame_style = "text_only"
        layout_suffix = _FRAME_STYLE_TO_LAYOUT.get(frame_style, "default")
        layout_class = f"layout-{layout_suffix}" if layout_suffix != "default" else ""

        # Build a 2-column layout: left = diagram, right = text (no panel).
        # Both columns are inside the clip div. GSAP animates them by id.
        inner_parts: List[str] = []

        # For centered layouts, skip the left column entirely
        is_centered = layout_suffix == "centered"

        if not is_centered:
            if has_image_bg:
                rel = _to_asset_url(visual, project_root)
                inner_parts.append(
                    f'<div class="left-col">'
                    f'  <img class="bg-image" src="{rel}" />'
                    f'</div>'
                )
            elif has_video_bg:
                rel = _to_asset_url(visual, project_root)
                inner_parts.append(
                    f'<div class="left-col">'
                    f'  <video class="scene-visual" src="{rel}" muted playsinline></video>'
                    f'</div>'
                )
            else:
                # No image available — show a placeholder gradient
                inner_parts.append(
                    f'<div class="left-col placeholder">'
                    f'  <div class="placeholder-text">{_html_escape(title_text)}</div>'
                    f'</div>'
                )

        # Right column content varies by frame_style
        if frame_style in ("title_hero", "text_only", "quote_callout"):
            # Centered layout: large title + body text, centered
            inner_parts.append(
                f'<div class="right-col">'
                f'  <div class="text-block centered">'
                f'    <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'    <p class="scene-body" id="body-{sid}">{body_text}</p>'
                f'  </div>'
                f'</div>'
            )
        elif frame_style == "listing_columns":
            # Parse narration into list items (split by newlines or numbered items)
            narration = scene.get("narration", "")
            items = _parse_listing_items(narration)
            listing_html = '<div class="listing-grid">'
            for item in items:
                item_title = _html_escape(item.get("title", ""))
                item_desc = _html_escape(item.get("desc", ""))
                listing_html += (
                    f'<div class="listing-item">'
                    f'<h3>{item_title}</h3>'
                    f'<p>{item_desc}</p>'
                    f'</div>'
                )
            listing_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {listing_html}'
                f'</div>'
            )
        elif frame_style == "steps_horizontal":
            # Parse narration into numbered steps
            narration = scene.get("narration", "")
            steps = _parse_steps(narration)
            steps_html = '<div class="steps-row">'
            for idx, step in enumerate(steps, 1):
                step_text = _html_escape(step)
                steps_html += (
                    f'<div class="step-item">'
                    f'<div class="step-number">{idx}</div>'
                    f'<div class="step-label">{step_text}</div>'
                    f'</div>'
                )
            steps_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {steps_html}'
                f'</div>'
            )
        elif frame_style == "stats_grid":
            # Parse narration into 4 key stats/points
            narration = scene.get("narration", "")
            stats = _parse_stats(narration)
            stats_html = '<div class="stats-grid">'
            for stat in stats:
                stat_value = _html_escape(stat.get("value", ""))
                stat_label = _html_escape(stat.get("label", ""))
                stats_html += (
                    f'<div class="stat-card">'
                    f'<div class="stat-value">{stat_value}</div>'
                    f'<div class="stat-label">{stat_label}</div>'
                    f'</div>'
                )
            stats_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {stats_html}'
                f'</div>'
            )
        elif frame_style == "chapter_marker":
            # Large number + title
            chapter_num = scene.get("chapter_number", str(sid))
            inner_parts.append(
                f'<div class="right-col">'
                f'  <div class="chapter-number">{_html_escape(chapter_num)}</div>'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  <p class="scene-body" id="body-{sid}">{body_text}</p>'
                f'</div>'
            )
        elif frame_style == "type_columns":
            # Multi-column layout for types/categories
            narration = scene.get("narration", "")
            items = _parse_type_items(narration)
            type_html = '<div class="type-columns">'
            for idx, item in enumerate(items):
                item_title = _html_escape(item.get("title", ""))
                item_desc = _html_escape(item.get("desc", ""))
                accent_var = f"var(--accent{(idx % 4) + 1})" if idx < 4 else "var(--accent)"
                type_html += (
                    f'<div class="type-card" id="type-{sid}-{idx}">'
                    f'  <div class="type-icon" style="background:{accent_var}">'
                    f'    <span class="type-number">{idx + 1}</span>'
                    f'  </div>'
                    f'  <h3 class="type-title">{item_title}</h3>'
                    f'  <p class="type-desc">{item_desc}</p>'
                    f'</div>'
                )
            type_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {type_html}'
                f'</div>'
            )
        elif frame_style == "flow_chain":
            # Connected nodes showing a process/cycle with SVG arrows
            narration = scene.get("narration", "")
            steps = _parse_flow_steps(narration)
            n = len(steps)
            # SVG dimensions
            svg_w = max(700, n * 150)
            node_spacing = svg_w / (n + 1)
            node_y = 60
            node_r = 28
            # Start SVG
            flow_html = f'<div class="flow-chain"><svg class="flow-svg" viewBox="0 0 {svg_w} 140" xmlns="http://www.w3.org/2000/svg">'
            flow_html += '<defs><marker id="flow-arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="var(--accent)"/></marker></defs>'
            # Draw arrows first (behind nodes)
            for idx in range(n - 1):
                x1 = node_spacing * (idx + 1) + node_r + 4
                x2 = node_spacing * (idx + 2) - node_r - 4
                flow_html += (
                    f'<line class="flow-arrow-svg" id="flow-arrow-{sid}-{idx}" '
                    f'x1="{x1:.1f}" y1="{node_y}" x2="{x2:.1f}" y2="{node_y}" '
                    f'stroke="var(--accent)" stroke-width="2" marker-end="url(#flow-arrowhead)"/>'
                )
            flow_html += '</svg>'
            # Draw nodes as positioned divs
            flow_html += '<div class="flow-nodes">'
            for idx, step in enumerate(steps):
                step_text = _html_escape(step)
                accent_var = f"var(--accent{(idx % 4) + 1})" if idx < 4 else "var(--accent)"
                left_pct = (node_spacing * (idx + 1) / svg_w) * 100
                flow_html += (
                    f'<div class="flow-node" id="flow-{sid}-{idx}" style="left:{left_pct:.1f}%">'
                    f'  <div class="flow-circle" style="border-color:{accent_var}">'
                    f'    <span class="flow-number">{idx + 1}</span>'
                    f'  </div>'
                    f'  <div class="flow-label">{step_text}</div>'
                    f'</div>'
                )
            flow_html += '</div></div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {flow_html}'
                f'</div>'
            )
        elif frame_style == "process_flow":
            # Linear input → process → output diagram with SVG arrows
            narration = scene.get("narration", "")
            steps = _parse_flow_steps(narration)
            # Split into input/transform/output
            n = len(steps)
            if n >= 3:
                inputs = steps[:n//3]
                transform = steps[n//3:2*n//3]
                outputs = steps[2*n//3:]
            elif n == 2:
                inputs = [steps[0]]
                transform = [steps[0]]
                outputs = [steps[1]]
            else:
                inputs = steps
                transform = ["Process"]
                outputs = steps

            proc_html = '<div class="process-flow">'
            # Input column
            proc_html += '<div class="process-col process-input"><div class="process-col-title">Input</div>'
            for s in inputs:
                proc_html += f'<div class="process-item">{_html_escape(s)}</div>'
            proc_html += '</div>'
            # SVG Arrow
            proc_html += '<svg class="process-arrow-svg" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">'
            proc_html += '<defs><marker id="proc-arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="var(--accent)"/></marker></defs>'
            proc_html += '<line class="process-arrow-line" id="proc-arrow-1" x1="5" y1="30" x2="50" y2="30" stroke="var(--accent)" stroke-width="3" marker-end="url(#proc-arrowhead)"/></svg>'
            # Transform column
            proc_html += '<div class="process-col process-transform"><div class="process-col-title">Process</div>'
            for s in transform:
                proc_html += f'<div class="process-item">{_html_escape(s)}</div>'
            proc_html += '</div>'
            # SVG Arrow
            proc_html += '<svg class="process-arrow-svg" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg">'
            proc_html += '<line class="process-arrow-line" id="proc-arrow-2" x1="5" y1="30" x2="50" y2="30" stroke="var(--accent)" stroke-width="3" marker-end="url(#proc-arrowhead)"/></svg>'
            # Output column
            proc_html += '<div class="process-col process-output"><div class="process-col-title">Output</div>'
            for s in outputs:
                proc_html += f'<div class="process-item">{_html_escape(s)}</div>'
            proc_html += '</div>'
            proc_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {proc_html}'
                f'</div>'
            )
        elif frame_style == "infographic":
            # Complex multi-element diagram with stats + icons
            narration = scene.get("narration", "")
            stats = _parse_stats(narration)
            items = _parse_type_items(narration)
            inf_html = '<div class="infographic">'
            # Stats row at top
            inf_html += '<div class="infographic-stats">'
            for stat in stats:
                inf_html += (
                    f'<div class="infographic-stat">'
                    f'  <div class="infographic-stat-value">{_html_escape(stat.get("value", ""))}</div>'
                    f'  <div class="infographic-stat-label">{_html_escape(stat.get("label", ""))}</div>'
                    f'</div>'
                )
            inf_html += '</div>'
            # Items row below
            inf_html += '<div class="infographic-items">'
            for idx, item in enumerate(items):
                inf_html += (
                    f'<div class="infographic-item">'
                    f'  <h4>{_html_escape(item.get("title", ""))}</h4>'
                    f'  <p>{_html_escape(item.get("desc", ""))}</p>'
                    f'</div>'
                )
            inf_html += '</div></div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {inf_html}'
                f'</div>'
            )
        elif frame_style == "venn_diagram":
            narration = scene.get("narration", "")
            sets = _parse_venn_items(narration)
            venn_html = '<div class="venn-container"><svg class="venn-svg" viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">'
            colors = ["var(--accent)", "var(--accent2)", "var(--accent3)"]
            cx_positions = [190, 310, 250]
            cy_positions = [160, 160, 180]
            for idx, s in enumerate(sets[:3]):
                cx = cx_positions[idx] if idx < len(cx_positions) else 250
                cy = cy_positions[idx] if idx < len(cy_positions) else 160
                color = colors[idx] if idx < len(colors) else "var(--accent)"
                venn_html += (
                    f'<circle class="venn-circle" id="venn-{sid}-{idx}" '
                    f'cx="{cx}" cy="{cy}" r="90" '
                    f'fill="{color}" fill-opacity="0.3" stroke="{color}" stroke-width="2"/>'
                )
            venn_html += '</svg><div class="venn-labels">'
            for idx, s in enumerate(sets[:3]):
                venn_html += (
                    f'<div class="venn-label" id="venn-label-{sid}-{idx}">'
                    f'<strong>{_html_escape(s.get("name", ""))}</strong>'
                    f'<br><small>{_html_escape(s.get("values", ""))}</small></div>'
                )
            venn_html += '</div></div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {venn_html}'
                f'</div>'
            )
        elif frame_style == "pyramid":
            narration = scene.get("narration", "")
            levels = _parse_pyramid_items(narration)
            pyramid_html = '<div class="pyramid-container">'
            n = len(levels)
            for idx, level in enumerate(levels):
                # Width decreases from bottom to top
                width_pct = 100 - (idx * (60 / max(n - 1, 1)))
                pyramid_html += (
                    f'<div class="pyramid-level" id="pyramid-{sid}-{idx}" '
                    f'style="width:{width_pct}%">'
                    f'  <div class="pyramid-label">{_html_escape(level.get("label", ""))}</div>'
                    f'  <div class="pyramid-desc">{_html_escape(level.get("desc", ""))}</div>'
                    f'</div>'
                )
            pyramid_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {pyramid_html}'
                f'</div>'
            )
        elif frame_style == "cycle_diagram":
            narration = scene.get("narration", "")
            steps = _parse_cycle_items(narration)
            n = len(steps)
            cycle_html = '<div class="cycle-container"><svg class="cycle-svg" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">'
            # Draw connecting arrows
            for idx in range(n):
                angle1 = (idx / n) * 360 - 90
                angle2 = ((idx + 1) / n) * 360 - 90
                x1 = 200 + 130 * math.cos(math.radians(angle1))
                y1 = 200 + 130 * math.sin(math.radians(angle1))
                x2 = 200 + 130 * math.cos(math.radians(angle2))
                y2 = 200 + 130 * math.sin(math.radians(angle2))
                cycle_html += (
                    f'<line class="cycle-arrow" id="cycle-arrow-{sid}-{idx}" '
                    f'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                    f'stroke="var(--accent)" stroke-width="2" marker-end="url(#arrowhead)"/>'
                )
            cycle_html += '<defs><marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="var(--accent)"/></marker></defs>'
            # Draw nodes
            for idx, step in enumerate(steps):
                angle = (idx / n) * 360 - 90
                x = 200 + 130 * math.cos(math.radians(angle))
                y = 200 + 130 * math.sin(math.radians(angle))
                color = f"var(--accent{(idx % 4) + 1})" if idx < 4 else "var(--accent)"
                cycle_html += (
                    f'<circle class="cycle-node" id="cycle-node-{sid}-{idx}" '
                    f'cx="{x:.1f}" cy="{y:.1f}" r="35" '
                    f'fill="{color}" fill-opacity="0.9"/>'
                    f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
                    f'dy="0.35em" fill="white" font-size="11" font-weight="600">'
                    f'{idx + 1}</text>'
                )
            cycle_html += '</svg><div class="cycle-labels">'
            for idx, step in enumerate(steps):
                cycle_html += f'<div class="cycle-label" id="cycle-label-{sid}-{idx}">{_html_escape(step)}</div>'
            cycle_html += '</div></div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {cycle_html}'
                f'</div>'
            )
        elif frame_style == "funnel":
            narration = scene.get("narration", "")
            stages = _parse_funnel_items(narration)
            funnel_html = '<div class="funnel-container">'
            n = len(stages)
            for idx, stage in enumerate(stages):
                width_pct = 100 - (idx * (50 / max(n - 1, 1)))
                color = f"var(--accent{(idx % 4) + 1})" if idx < 4 else "var(--accent)"
                funnel_html += (
                    f'<div class="funnel-stage" id="funnel-{sid}-{idx}" '
                    f'style="width:{width_pct}%; background:{color}">'
                    f'  <span>{_html_escape(stage)}</span>'
                    f'</div>'
                )
            funnel_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {funnel_html}'
                f'</div>'
            )
        elif frame_style == "flowchart":
            narration = scene.get("narration", "")
            nodes = _parse_flowchart_items(narration)
            flowchart_html = '<div class="flowchart-container">'
            for idx, node in enumerate(nodes):
                node_type = node.get("type", "process")
                label = _html_escape(node.get("label", ""))
                if node_type == "decision":
                    flowchart_html += (
                        f'<div class="flowchart-node flowchart-decision" id="fc-{sid}-{idx}">'
                        f'  <div class="diamond"><span>{label}</span></div>'
                        f'</div>'
                    )
                elif node_type == "start" or node_type == "end":
                    flowchart_html += (
                        f'<div class="flowchart-node flowchart-{node_type}" id="fc-{sid}-{idx}">'
                        f'  <div class="oval"><span>{label}</span></div>'
                        f'</div>'
                    )
                else:
                    flowchart_html += (
                        f'<div class="flowchart-node flowchart-process" id="fc-{sid}-{idx}">'
                        f'  <div class="rect"><span>{label}</span></div>'
                        f'</div>'
                    )
                if idx < len(nodes) - 1:
                    flowchart_html += (
                        f'<svg class="flowchart-arrow-svg" id="fc-arrow-{sid}-{idx}" '
                        f'viewBox="0 0 30 40" xmlns="http://www.w3.org/2000/svg">'
                        f'<defs><marker id="fc-arrowhead-{sid}-{idx}" markerWidth="8" markerHeight="6" '
                        f'refX="8" refY="3" orient="auto">'
                        f'<polygon points="0 0, 8 3, 0 6" fill="var(--accent)"/></marker></defs>'
                        f'<line x1="15" y1="2" x2="15" y2="32" stroke="var(--accent)" stroke-width="2" '
                        f'marker-end="url(#fc-arrowhead-{sid}-{idx})"/></svg>'
                    )
            flowchart_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {flowchart_html}'
                f'</div>'
            )
        elif frame_style == "pie_chart":
            narration = scene.get("narration", "")
            slices_data = _parse_pie_data(narration)
            total = sum(s.get("percent", 0) for s in slices_data)
            if total == 0:
                total = 100
            colors = ["#e94560", "#4fc3f7", "#f5a623", "#7c4dff", "#4caf50", "#ff6b6b"]
            pie_html = '<div class="pie-container"><svg class="pie-svg" viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">'
            cumulative = 0
            for idx, s in enumerate(slices_data):
                pct = s.get("percent", 0) / total
                start_angle = cumulative * 360
                end_angle = (cumulative + pct) * 360
                cumulative += pct
                x1 = 150 + 120 * math.cos(math.radians(start_angle - 90))
                y1 = 150 + 120 * math.sin(math.radians(start_angle - 90))
                x2 = 150 + 120 * math.cos(math.radians(end_angle - 90))
                y2 = 150 + 120 * math.sin(math.radians(end_angle - 90))
                large_arc = 1 if pct > 0.5 else 0
                color = colors[idx % len(colors)]
                pie_html += (
                    f'<path class="pie-slice" id="pie-{sid}-{idx}" '
                    f'd="M150,150 L{x1:.1f},{y1:.1f} A120,120 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" '
                    f'fill="{color}" fill-opacity="0.85" stroke="var(--bg-dark)" stroke-width="2"/>'
                )
            pie_html += '</svg><div class="pie-legend">'
            for idx, s in enumerate(slices_data):
                color = colors[idx % len(colors)]
                pie_html += (
                    f'<div class="pie-legend-item" id="pie-legend-{sid}-{idx}">'
                    f'  <span class="pie-color" style="background:{color}"></span>'
                    f'  <span>{_html_escape(s.get("label", ""))} ({s.get("percent", 0):.0f}%)</span>'
                    f'</div>'
                )
            pie_html += '</div></div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {pie_html}'
                f'</div>'
            )
        elif frame_style == "bar_chart":
            narration = scene.get("narration", "")
            bars_data = _parse_bar_data(narration)
            max_val = max((b.get("value", 0) for b in bars_data), default=1) or 1
            colors = ["#e94560", "#4fc3f7", "#f5a623", "#7c4dff", "#4caf50", "#ff6b6b", "#45b7d1", "#96ceb4"]
            bar_html = '<div class="bar-chart-container">'
            for idx, bar in enumerate(bars_data):
                val = bar.get("value", 0)
                height_pct = (val / max_val) * 100
                color = colors[idx % len(colors)]
                bar_html += (
                    f'<div class="bar-col" id="bar-{sid}-{idx}">'
                    f'  <div class="bar-value">{val:.0f}</div>'
                    f'  <div class="bar-fill" style="height:{height_pct}%; background:{color}"></div>'
                    f'  <div class="bar-label">{_html_escape(bar.get("label", ""))}</div>'
                    f'</div>'
                )
            bar_html += '</div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {bar_html}'
                f'</div>'
            )
        elif frame_style == "annotated_diagram":
            narration = scene.get("narration", "")
            annotations = _parse_annotation_items(narration)
            ann_html = '<div class="annotated-container"><div class="annotated-center">'
            # Central placeholder (image or gradient)
            if has_image_bg:
                rel = _to_asset_url(visual, project_root)
                ann_html += f'<img class="annotated-image" src="{rel}" />'
            else:
                ann_html += f'<div class="annotated-placeholder">{title_text}</div>'
            ann_html += '</div><div class="annotated-labels">'
            for idx, ann in enumerate(annotations):
                pos = ann.get("pos", "top")
                ann_html += (
                    f'<div class="annotated-label annotated-{pos}" id="ann-{sid}-{idx}">'
                    f'  <div class="annotated-dot"></div>'
                    f'  <div class="annotated-text">'
                    f'    <strong>{_html_escape(ann.get("label", ""))}</strong>'
                    f'    <small>{_html_escape(ann.get("desc", ""))}</small>'
                    f'  </div>'
                    f'</div>'
                )
            ann_html += '</div></div>'
            inner_parts.append(
                f'<div class="right-col">'
                f'  <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'  {ann_html}'
                f'</div>'
            )
        else:
            # Default: text block (for image_left, diagram_center, split_compare, etc.)
            inner_parts.append(
                f'<div class="right-col">'
                f'  <div class="text-block">'
                f'    <h1 class="scene-title" id="title-{sid}">{title_text}</h1>'
                f'    <p class="scene-body" id="body-{sid}">{body_text}</p>'
                f'  </div>'
                f'</div>'
            )

        # Single clip per scene: the panel-wrap. All other per-scene content
        # (bg-image, title, body, accent bar) lives INSIDE this div as
        # regular DOM — no class="clip" — so the engine only tracks one
        # visibility boundary per scene on this track.
        layers.append(
            f'<div class="clip panel-wrap {layout_class}" id="panel-{sid}" '
            f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
            f'data-track-index="{TRACK_PANEL}">'
            f'  {"".join(inner_parts)}'
            f'</div>'
        )

        # per-scene audio — engine mixes via amix filter at the assemble stage
        audio = _find_audio(scene)
        if audio:
            audio_src = _to_audio_src(audio)
            layers.append(
                f'<audio class="clip" id="audio-{sid}" '
                f'data-start="{start:.3f}" data-duration="{dur:.3f}" '
                f'data-track-index="{TRACK_AUDIO}" src="{audio_src}"></audio>'
            )

        # flash transition between scenes
        if not is_last:
            trans_start = start + dur - CROSSFADE_S
            trans_dur = CROSSFADE_S * 2
            layers.append(
                f'<div class="clip scene-transition" id="trans-{sid}" '
                f'data-start="{trans_start:.3f}" data-duration="{trans_dur:.3f}" '
                f'data-track-index="{TRACK_TRANS}">'
                f'  <div class="trans-flash"></div>'
                f'</div>'
            )

    # ---------- CSS ----------
    css = f"""
    :root {{
      --bg-dark: {PALETTE['bg_dark']};
      --bg-mid: {PALETTE['bg_mid']};
      --bg-light: {PALETTE['bg_light']};
      --accent: {PALETTE['accent']};
      --accent2: {PALETTE['accent2']};
      --accent3: {PALETTE['accent3']};
      --accent4: {PALETTE['accent4']};
      --text: {PALETTE['text']};
      --text-dim: {PALETTE['text_dim']};
      --good: {PALETTE['good']};
      --panel-bg: {PALETTE['panel_bg']};
      --w: {WIDTH}px;
      --h: {HEIGHT}px;
    }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    html, body {{
      margin: 0; padding: 0;
      width: var(--w); height: var(--h);
      background: var(--bg-dark);
      color: var(--text);
      font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
      overflow: hidden;
    }}
    #root {{
      position: relative;
      width: var(--w);
      height: var(--h);
      overflow: hidden;
      background: var(--bg-dark);
    }}
    .bg-gradient {{
      position: absolute; inset: 0;
      background: linear-gradient(135deg, var(--bg-dark) 0%, var(--bg-mid) 50%, var(--bg-light) 100%);
      z-index: 0;
    }}
    .chrome {{
      position: absolute; inset: 0;
      z-index: 1;
      pointer-events: none;
    }}
    .bg-orbs {{
      position: absolute; inset: 0;
      overflow: hidden;
    }}
    .orb {{
      position: absolute;
      border-radius: 50%;
      opacity: 0.35;
    }}
    .orb-a {{ width: 520px; height: 520px; background: var(--accent); top: -120px; left: -120px; filter: blur(120px); }}
    .orb-b {{ width: 600px; height: 600px; background: var(--accent4); bottom: -160px; right: -100px; filter: blur(120px); }}
    .orb-c {{ width: 420px; height: 420px; background: var(--accent2); top: 30%; right: 10%; filter: blur(120px); }}

    /* 2-column layout: left = diagram, right = text. No panel frames. */
    .panel-wrap {{
      position: absolute; inset: 0;
      z-index: 2;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0;
      padding: 0;
    }}

    .left-col {{
      position: relative;
      width: 100%;
      height: 100%;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .left-col.placeholder {{
      background: linear-gradient(135deg, var(--bg-mid) 0%, var(--bg-light) 100%);
    }}
    .placeholder-text {{
      font-family: 'Space Grotesk', 'Inter', sans-serif;
      font-size: 48px;
      font-weight: 700;
      color: var(--text-dim);
      text-align: center;
      padding: 40px;
    }}
    .bg-image {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      opacity: 1;
      transform-origin: center;
    }}
    .scene-visual {{
      width: 100%;
      height: 100%;
      object-fit: contain;
    }}

    .right-col {{
      position: relative;
      width: 100%;
      height: 100%;
      padding: 80px 70px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: flex-start;
    }}
    .text-block {{
      display: block;
      width: 100%;
      max-width: 800px;
    }}
    .text-block.centered {{
      max-width: 1000px;
      text-align: center;
    }}
    .text-block.centered .scene-title {{
      font-size: 64px;
    }}
    .text-block.centered .scene-body {{
      font-size: 28px;
      max-width: 900px;
      margin-left: auto;
      margin-right: auto;
    }}
    .scene-title {{
      margin: 0 0 20px 0;
      font-family: 'Space Grotesk', 'Inter', sans-serif;
      font-size: 48px;
      font-weight: 700;
      line-height: 1.15;
      color: var(--text);
      letter-spacing: -0.01em;
    }}
    .scene-body {{
      margin: 0;
      font-size: 24px;
      line-height: 1.6;
      color: var(--text-dim);
      white-space: pre-wrap;
    }}

    .scene-transition {{
      position: absolute; inset: 0;
      z-index: 5;
      background: transparent;
    }}
    .trans-flash {{
      position: absolute; inset: 0;
      background: radial-gradient(circle at center, rgba(233,69,96,0.6) 0%, rgba(79,195,247,0.3) 40%, transparent 70%);
      opacity: 0;
    }}

    /* ===== NEW LAYOUT STYLES ===== */

    /* Centered layout (title_hero, text_only, quote_callout) */
    .panel-wrap.layout-centered {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-centered .left-col {{ display: none; }}
    .panel-wrap.layout-centered .right-col {{
      grid-column: 1;
      align-items: center;
      text-align: center;
    }}
    .panel-wrap.layout-centered .scene-title {{
      font-size: 64px;
      max-width: 1000px;
    }}
    .panel-wrap.layout-centered .scene-body {{
      font-size: 28px;
      max-width: 900px;
    }}

    /* Image right (text left, image right) */
    .panel-wrap.layout-image-right {{
      grid-template-columns: 1fr 1fr;
    }}
    .panel-wrap.layout-image-right .left-col {{ order: 2; }}
    .panel-wrap.layout-image-right .right-col {{ order: 1; }}

    /* Listing columns (3-column grid for lists) */
    .panel-wrap.layout-listing {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-listing .left-col {{ display: none; }}
    .panel-wrap.layout-listing .right-col {{
      grid-column: 1;
      padding: 60px 80px;
    }}
    .listing-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 24px;
      width: 100%;
    }}
    .listing-item {{
      background: var(--panel-bg);
      border-radius: 12px;
      padding: 24px;
      border-left: 3px solid var(--accent);
    }}
    .listing-item h3 {{
      margin: 0 0 8px 0;
      font-size: 20px;
      color: var(--accent);
    }}
    .listing-item p {{
      margin: 0;
      font-size: 16px;
      color: var(--text-dim);
      line-height: 1.4;
    }}

    /* Full bleed (full-screen image with text overlay) */
    .panel-wrap.layout-full-bleed {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-full-bleed .left-col {{
      position: absolute;
      inset: 0;
      z-index: 0;
    }}
    .panel-wrap.layout-full-bleed .bg-image {{
      object-fit: cover;
    }}
    .panel-wrap.layout-full-bleed .right-col {{
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 1;
      background: linear-gradient(transparent, rgba(10,14,39,0.95));
      padding: 80px 70px;
      justify-content: flex-end;
    }}
    .panel-wrap.layout-full-bleed .scene-title {{
      font-size: 56px;
    }}

    /* Horizontal steps (numbered timeline) */
    .panel-wrap.layout-steps-horizontal {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-steps-horizontal .left-col {{ display: none; }}
    .panel-wrap.layout-steps-horizontal .right-col {{
      grid-column: 1;
      padding: 60px 80px;
    }}
    .steps-row {{
      display: flex;
      gap: 32px;
      width: 100%;
      margin-top: 24px;
    }}
    .step-item {{
      flex: 1;
      text-align: center;
    }}
    .step-number {{
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      font-weight: 700;
      color: var(--text);
      margin: 0 auto 12px;
    }}
    .step-label {{
      font-size: 16px;
      color: var(--text-dim);
      line-height: 1.3;
    }}

    /* Stats grid (2x2 key points) */
    .panel-wrap.layout-stats-grid {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-stats-grid .left-col {{ display: none; }}
    .panel-wrap.layout-stats-grid .right-col {{
      grid-column: 1;
      padding: 60px 80px;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      width: 100%;
    }}
    .stat-card {{
      background: var(--panel-bg);
      border-radius: 16px;
      padding: 32px;
      text-align: center;
      border-top: 3px solid var(--accent);
    }}
    .stat-card:nth-child(2) {{ border-top-color: var(--accent2); }}
    .stat-card:nth-child(3) {{ border-top-color: var(--accent3); }}
    .stat-card:nth-child(4) {{ border-top-color: var(--accent4); }}
    .stat-value {{
      font-size: 42px;
      font-weight: 800;
      color: var(--accent);
      line-height: 1;
    }}
    .stat-card:nth-child(2) .stat-value {{ color: var(--accent2); }}
    .stat-card:nth-child(3) .stat-value {{ color: var(--accent3); }}
    .stat-card:nth-child(4) .stat-value {{ color: var(--accent4); }}
    .stat-label {{
      font-size: 16px;
      color: var(--text-dim);
      margin-top: 8px;
      line-height: 1.3;
    }}

    /* Chapter marker (section divider) */
    .panel-wrap.layout-chapter-marker {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-chapter-marker .left-col {{ display: none; }}
    .panel-wrap.layout-chapter-marker .right-col {{
      grid-column: 1;
      align-items: center;
      text-align: center;
      justify-content: center;
    }}
    .chapter-number {{
      font-size: 140px;
      font-weight: 900;
      color: var(--accent);
      opacity: 0.25;
      line-height: 1;
      margin-bottom: -30px;
    }}
    .panel-wrap.layout-chapter-marker .scene-title {{
      font-size: 52px;
      position: relative;
      z-index: 1;
    }}

    /* ===== COMPLEX DIAGRAM LAYOUTS ===== */

    /* Type columns (multi-column cards for types/categories) */
    .panel-wrap.layout-type-columns {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-type-columns .left-col {{ display: none; }}
    .panel-wrap.layout-type-columns .right-col {{
      grid-column: 1;
      padding: 50px 60px;
    }}
    .type-columns {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px;
      width: 100%;
      margin-top: 16px;
    }}
    .type-card {{
      background: var(--panel-bg);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      border-top: 3px solid var(--accent);
      opacity: 0;
      transform: translateY(20px);
    }}
    .type-card:nth-child(2) {{ border-top-color: var(--accent2); }}
    .type-card:nth-child(3) {{ border-top-color: var(--accent3); }}
    .type-card:nth-child(4) {{ border-top-color: var(--accent4); }}
    .type-card:nth-child(5) {{ border-top-color: var(--good); }}
    .type-card:nth-child(6) {{ border-top-color: var(--accent); }}
    .type-icon {{
      width: 48px;
      height: 48px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 12px;
    }}
    .type-number {{
      font-size: 20px;
      font-weight: 800;
      color: var(--text);
    }}
    .type-title {{
      margin: 0 0 8px 0;
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
    }}
    .type-desc {{
      margin: 0;
      font-size: 14px;
      color: var(--text-dim);
      line-height: 1.4;
    }}

    /* Flow chain (connected nodes with arrows) */
    .panel-wrap.layout-flow-chain {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-flow-chain .left-col {{ display: none; }}
    .panel-wrap.layout-flow-chain .right-col {{
      grid-column: 1;
      padding: 50px 60px;
    }}
    .flow-chain {{
      position: relative;
      width: 100%;
      margin-top: 20px;
      min-height: 140px;
    }}
    .flow-svg {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 140px;
      pointer-events: none;
    }}
    .flow-nodes {{
      position: relative;
      width: 100%;
      height: 140px;
    }}
    .flow-node {{
      position: absolute;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      max-width: 140px;
      transform: translateX(-50%);
      opacity: 0;
      transform: translateX(-50%) scale(0.8);
    }}
    .flow-circle {{
      width: 56px;
      height: 56px;
      border-radius: 50%;
      border: 3px solid var(--accent);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 10px;
      background: var(--bg-mid);
    }}
    .flow-number {{
      font-size: 22px;
      font-weight: 800;
      color: var(--text);
    }}
    .flow-label {{
      font-size: 13px;
      color: var(--text-dim);
      line-height: 1.3;
      max-width: 130px;
    }}
    .flow-arrow-svg {{
      opacity: 0;
    }}

    /* Process flow (input → transform → output) */
    .panel-wrap.layout-process-flow {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-process-flow .left-col {{ display: none; }}
    .panel-wrap.layout-process-flow .right-col {{
      grid-column: 1;
      padding: 50px 60px;
    }}
    .process-flow {{
      display: grid;
      grid-template-columns: 1fr 60px 1fr 60px 1fr;
      gap: 0;
      width: 100%;
      margin-top: 20px;
      align-items: start;
    }}
    .process-col {{
      background: var(--panel-bg);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      opacity: 0;
      transform: translateX(-20px);
    }}
    .process-transform {{
      border-top: 3px solid var(--accent3);
    }}
    .process-output {{
      border-top: 3px solid var(--good);
    }}
    .process-col-title {{
      font-size: 16px;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .process-item {{
      font-size: 14px;
      color: var(--text-dim);
      padding: 6px 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }}
    .process-item:last-child {{ border-bottom: none; }}
    .process-arrow-svg {{
      width: 60px;
      height: 60px;
      margin-top: 40px;
      opacity: 0;
      transform: translateX(-10px);
    }}

    /* Infographic (complex multi-element) */
    .panel-wrap.layout-infographic {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-infographic .left-col {{ display: none; }}
    .panel-wrap.layout-infographic .right-col {{
      grid-column: 1;
      padding: 50px 60px;
    }}
    .infographic {{
      width: 100%;
      margin-top: 16px;
    }}
    .infographic-stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }}
    .infographic-stat {{
      background: var(--panel-bg);
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      border-top: 3px solid var(--accent);
      opacity: 0;
      transform: translateY(15px);
    }}
    .infographic-stat:nth-child(2) {{ border-top-color: var(--accent2); }}
    .infographic-stat:nth-child(3) {{ border-top-color: var(--accent3); }}
    .infographic-stat:nth-child(4) {{ border-top-color: var(--accent4); }}
    .infographic-stat-value {{
      font-size: 28px;
      font-weight: 800;
      color: var(--accent);
      line-height: 1;
    }}
    .infographic-stat:nth-child(2) .infographic-stat-value {{ color: var(--accent2); }}
    .infographic-stat:nth-child(3) .infographic-stat-value {{ color: var(--accent3); }}
    .infographic-stat:nth-child(4) .infographic-stat-value {{ color: var(--accent4); }}
    .infographic-stat-label {{
      font-size: 13px;
      color: var(--text-dim);
      margin-top: 6px;
    }}
    .infographic-items {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .infographic-item {{
      background: rgba(15, 52, 96, 0.5);
      border-radius: 8px;
      padding: 14px;
      opacity: 0;
      transform: translateY(10px);
    }}
    .infographic-item h4 {{
      margin: 0 0 4px 0;
      font-size: 14px;
      color: var(--accent2);
    }}
    .infographic-item p {{
      margin: 0;
      font-size: 12px;
      color: var(--text-dim);
      line-height: 1.3;
    }}

    /* ===== DIAGRAM LAYOUTS ===== */

    /* Venn Diagram */
    .panel-wrap.layout-venn-diagram {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-venn-diagram .left-col {{ display: none; }}
    .panel-wrap.layout-venn-diagram .right-col {{
      grid-column: 1;
      padding: 40px 60px;
    }}
    .venn-container {{
      display: flex;
      flex-direction: column;
      align-items: center;
      width: 100%;
      margin-top: 12px;
    }}
    .venn-svg {{
      width: 100%;
      max-width: 500px;
      height: auto;
    }}
    .venn-circle {{
      opacity: 0;
      transform-origin: center;
    }}
    .venn-labels {{
      display: flex;
      justify-content: center;
      gap: 24px;
      margin-top: 12px;
      flex-wrap: wrap;
    }}
    .venn-label {{
      text-align: center;
      font-size: 14px;
      color: var(--text-dim);
      opacity: 0;
      transform: translateY(10px);
    }}
    .venn-label strong {{
      color: var(--text);
      font-size: 15px;
    }}

    /* Pyramid */
    .panel-wrap.layout-pyramid {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-pyramid .left-col {{ display: none; }}
    .panel-wrap.layout-pyramid .right-col {{
      grid-column: 1;
      padding: 40px 60px;
    }}
    .pyramid-container {{
      display: flex;
      flex-direction: column-reverse;
      align-items: center;
      width: 100%;
      margin-top: 12px;
      gap: 4px;
    }}
    .pyramid-level {{
      padding: 14px 20px;
      text-align: center;
      border-radius: 6px;
      opacity: 0;
      transform: scaleX(0.8);
    }}
    .pyramid-level:nth-child(odd) {{ background: var(--accent); }}
    .pyramid-level:nth-child(even) {{ background: var(--accent2); }}
    .pyramid-label {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
    }}
    .pyramid-desc {{
      font-size: 12px;
      color: rgba(255,255,255,0.8);
      margin-top: 2px;
    }}

    /* Cycle Diagram */
    .panel-wrap.layout-cycle-diagram {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-cycle-diagram .left-col {{ display: none; }}
    .panel-wrap.layout-cycle-diagram .right-col {{
      grid-column: 1;
      padding: 30px 60px;
    }}
    .cycle-container {{
      display: flex;
      flex-direction: column;
      align-items: center;
      width: 100%;
      margin-top: 8px;
    }}
    .cycle-svg {{
      width: 320px;
      height: 320px;
    }}
    .cycle-node {{
      opacity: 0;
      transform-origin: center;
    }}
    .cycle-arrow {{
      opacity: 0;
    }}
    .cycle-labels {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 8px;
      margin-top: 8px;
    }}
    .cycle-label {{
      font-size: 12px;
      color: var(--text-dim);
      background: var(--panel-bg);
      padding: 4px 10px;
      border-radius: 4px;
      opacity: 0;
    }}

    /* Funnel */
    .panel-wrap.layout-funnel {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-funnel .left-col {{ display: none; }}
    .panel-wrap.layout-funnel .right-col {{
      grid-column: 1;
      padding: 40px 60px;
    }}
    .funnel-container {{
      display: flex;
      flex-direction: column;
      align-items: center;
      width: 100%;
      margin-top: 16px;
      gap: 6px;
    }}
    .funnel-stage {{
      padding: 16px 24px;
      text-align: center;
      border-radius: 8px;
      color: var(--text);
      font-size: 16px;
      font-weight: 600;
      opacity: 0;
      transform: scaleX(0.7);
    }}

    /* Flowchart */
    .panel-wrap.layout-flowchart {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-flowchart .left-col {{ display: none; }}
    .panel-wrap.layout-flowchart .right-col {{
      grid-column: 1;
      padding: 40px 50px;
    }}
    .flowchart-container {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      margin-top: 12px;
    }}
    .flowchart-node {{
      opacity: 0;
      transform: scale(0.8);
    }}
    .flowchart-node .rect {{
      background: var(--panel-bg);
      border: 2px solid var(--accent);
      border-radius: 8px;
      padding: 12px 18px;
      text-align: center;
      font-size: 13px;
      color: var(--text);
    }}
    .flowchart-node .diamond {{
      background: var(--panel-bg);
      border: 2px solid var(--accent3);
      padding: 12px 18px;
      text-align: center;
      font-size: 13px;
      color: var(--text);
      transform: rotate(45deg);
      border-radius: 4px;
    }}
    .flowchart-node .diamond span {{
      display: block;
      transform: rotate(-45deg);
    }}
    .flowchart-node .oval {{
      background: var(--accent);
      border-radius: 50px;
      padding: 12px 20px;
      text-align: center;
      font-size: 13px;
      color: var(--text);
      font-weight: 600;
    }}
    .flowchart-arrow-svg {{
      width: 30px;
      height: 40px;
      opacity: 0;
      flex-shrink: 0;
    }}

    /* Pie Chart */
    .panel-wrap.layout-pie-chart {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-pie-chart .left-col {{ display: none; }}
    .panel-wrap.layout-pie-chart .right-col {{
      grid-column: 1;
      padding: 40px 60px;
    }}
    .pie-container {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 32px;
      width: 100%;
      margin-top: 12px;
    }}
    .pie-svg {{
      width: 220px;
      height: 220px;
    }}
    .pie-slice {{
      opacity: 0;
      transform-origin: 150px 150px;
    }}
    .pie-legend {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .pie-legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      color: var(--text-dim);
      opacity: 0;
      transform: translateX(10px);
    }}
    .pie-color {{
      width: 14px;
      height: 14px;
      border-radius: 3px;
      flex-shrink: 0;
    }}

    /* Bar Chart */
    .panel-wrap.layout-bar-chart {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-bar-chart .left-col {{ display: none; }}
    .panel-wrap.layout-bar-chart .right-col {{
      grid-column: 1;
      padding: 40px 60px;
    }}
    .bar-chart-container {{
      display: flex;
      align-items: flex-end;
      justify-content: center;
      gap: 20px;
      width: 100%;
      height: 280px;
      margin-top: 16px;
      padding-bottom: 30px;
      border-bottom: 2px solid rgba(255,255,255,0.1);
    }}
    .bar-col {{
      display: flex;
      flex-direction: column;
      align-items: center;
      flex: 1;
      max-width: 80px;
      height: 100%;
      justify-content: flex-end;
      opacity: 0;
      transform: translateY(20px);
    }}
    .bar-fill {{
      width: 100%;
      border-radius: 6px 6px 0 0;
      min-height: 4px;
    }}
    .bar-value {{
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 4px;
    }}
    .bar-label {{
      font-size: 11px;
      color: var(--text-dim);
      text-align: center;
      margin-top: 6px;
      word-break: break-word;
    }}

    /* Annotated Diagram */
    .panel-wrap.layout-annotated-diagram {{
      grid-template-columns: 1fr;
    }}
    .panel-wrap.layout-annotated-diagram .left-col {{ display: none; }}
    .panel-wrap.layout-annotated-diagram .right-col {{
      grid-column: 1;
      padding: 30px 50px;
    }}
    .annotated-container {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      margin-top: 8px;
      gap: 24px;
    }}
    .annotated-center {{
      width: 240px;
      height: 240px;
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, var(--bg-mid), var(--bg-light));
      flex-shrink: 0;
    }}
    .annotated-image {{
      width: 100%;
      height: 100%;
      object-fit: contain;
    }}
    .annotated-placeholder {{
      font-size: 18px;
      font-weight: 700;
      color: var(--text-dim);
      text-align: center;
      padding: 20px;
    }}
    .annotated-labels {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .annotated-label {{
      display: flex;
      align-items: center;
      gap: 10px;
      opacity: 0;
      transform: translateX(15px);
    }}
    .annotated-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent);
      flex-shrink: 0;
    }}
    .annotated-text {{
      font-size: 13px;
      color: var(--text-dim);
    }}
    .annotated-text strong {{
      color: var(--text);
      display: block;
      font-size: 14px;
    }}

    /* ===== ANIMATION ENHANCEMENTS ===== */

    /* Wave stagger effect for listing/type cards */
    .listing-item, .type-card, .infographic-item {{
      transition: transform 0.3s ease, box-shadow 0.3s ease;
    }}
    .listing-item:hover, .type-card:hover, .infographic-item:hover {{
      transform: translateY(-4px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }}

    /* Elastic bounce for flow/cycle nodes */
    .flow-node, .cycle-node, .flowchart-node {{
      transition: transform 0.2s ease;
    }}

    /* SVG path drawing for cycle arrows */
    .cycle-arrow {{
      stroke-dasharray: 200;
      stroke-dashoffset: 200;
    }}
    .cycle-arrow.drawn {{
      stroke-dashoffset: 0;
      transition: stroke-dashoffset 0.6s ease;
    }}

    /* Color pulse for accent elements */
    .stat-card, .pie-slice, .bar-fill, .funnel-stage {{
      animation: colorPulse 3s ease-in-out infinite alternate;
    }}
    @keyframes colorPulse {{
      0% {{ filter: brightness(1); }}
      100% {{ filter: brightness(1.15); }}
    }}

    /* 3D card flip for type cards */
    .type-card {{
      perspective: 600px;
    }}
    .type-card .type-inner {{
      transition: transform 0.6s ease;
      transform-style: preserve-3d;
    }}
    .type-card.flipped .type-inner {{
      transform: rotateY(180deg);
    }}
    .type-card .type-front, .type-card .type-back {{
      backface-visibility: hidden;
    }}
    .type-card .type-back {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      transform: rotateY(180deg);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      background: var(--bg-mid);
      border-radius: 12px;
    }}

    /* Progress bar for steps */
    .step-progress {{
      height: 3px;
      background: rgba(255,255,255,0.1);
      border-radius: 2px;
      margin-top: 16px;
      overflow: hidden;
    }}
    .step-progress-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      border-radius: 2px;
      width: 0%;
      transition: width 0.3s ease;
    }}

    /* Glow effect for key elements */
    .glow {{
      box-shadow: 0 0 20px rgba(233, 69, 96, 0.4);
    }}

    /* Stagger wave animation */
    @keyframes staggerWave {{
      0% {{ opacity: 0; transform: translateY(20px); }}
      100% {{ opacity: 1; transform: translateY(0); }}
    }}
    """

    # ---------- GSAP timeline ----------
    # Register a paused GSAP timeline on window.__timelines keyed by the
    # composition id. The engine seeks this timeline on every hf-seek event.
    # Animations: Ken Burns on bg-image, panel slide-in, accent bar sweep,
    # title reveal, body paragraph fade, and smooth exit.
    gsap_anim_chains: List[str] = []
    for i, (scene, start, dur) in enumerate(zip(scenes, starts, durs)):
        sid = scene.get("scene_id", i + 1)
        is_last = i == len(scenes) - 1
        visual = _find_visual(scene)
        has_bg = bool(
            visual and
            visual.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )

        # Background image Ken Burns (zoom + pan)
        if has_bg:
            gsap_anim_chains.append(
                f"  tl.fromTo('#panel-{sid} .bg-image', "
                f"{{scale:1.05}}, "
                f"{{scale:1.0, duration:{dur:.1f}, ease:'none'}}, {start:.3f});"
            )

        # Left column entrance: slide in from left
        gsap_anim_chains.append(
            f"  tl.fromTo('#panel-{sid} .left-col', "
            f"{{opacity:0, x:-60}}, "
            f"{{opacity:1, x:0, duration:0.7, ease:'power3.out'}}, {start:.3f});"
        )

        # Title reveal: clip-path wipe from left
        gsap_anim_chains.append(
            f"  tl.fromTo('#title-{sid}', "
            f"{{opacity:0, clipPath:'inset(0 100% 0 0)'}}, "
            f"{{opacity:1, clipPath:'inset(0 0% 0 0)', duration:0.6, ease:'power3.out'}}, {start + 0.3:.3f});"
        )

        # Body text: fade up
        gsap_anim_chains.append(
            f"  tl.fromTo('#body-{sid}', "
            f"{{opacity:0, y:20}}, "
            f"{{opacity:1, y:0, duration:0.5, ease:'power2.out'}}, {start + 0.5:.3f});"
        )

        # Complex diagram animations (staggered element entrance)
        frame_style = scene.get("frame_style", "")
        if frame_style == "type_columns":
            # Animate each type-card in sequence
            for idx in range(6):
                card_delay = start + 0.6 + idx * 0.15
                gsap_anim_chains.append(
                    f"  tl.fromTo('#type-{sid}-{idx}', "
                    f"{{opacity:0, y:20}}, "
                    f"{{opacity:1, y:0, duration:0.4, ease:'power2.out'}}, {card_delay:.3f});"
                )
        elif frame_style == "flow_chain":
            # Animate each flow-node and SVG arrow in sequence
            narration = scene.get("narration", "")
            steps = _parse_flow_steps(narration)
            for idx in range(len(steps)):
                node_delay = start + 0.6 + idx * 0.3
                gsap_anim_chains.append(
                    f"  tl.fromTo('#flow-{sid}-{idx}', "
                    f"{{opacity:0, scale:0.8}}, "
                    f"{{opacity:1, scale:1, duration:0.4, ease:'back.out(1.7)'}}, {node_delay:.3f});"
                )
                # SVG arrow appears after node
                if idx < len(steps) - 1:
                    arrow_delay = node_delay + 0.2
                    gsap_anim_chains.append(
                        f"  tl.fromTo('#flow-arrow-{sid}-{idx}', "
                        f"{{opacity:0}}, "
                        f"{{opacity:1, duration:0.3, ease:'power2.out'}}, {arrow_delay:.3f});"
                    )
        elif frame_style == "process_flow":
            # Animate columns and SVG arrows in sequence
            narration = scene.get("narration", "")
            steps = _parse_flow_steps(narration)
            n = len(steps)
            # 3 columns + 2 SVG arrows
            for col_idx in range(3):
                col_delay = start + 0.6 + col_idx * 0.4
                gsap_anim_chains.append(
                    f"  tl.fromTo('#panel-{sid} .process-col:nth-child({col_idx * 2 + 1})', "
                    f"{{opacity:0, x:-20}}, "
                    f"{{opacity:1, x:0, duration:0.5, ease:'power2.out'}}, {col_delay:.3f});"
                )
                if col_idx < 2:
                    arrow_delay = col_delay + 0.3
                    gsap_anim_chains.append(
                        f"  tl.fromTo('#panel-{sid} .process-arrow-svg:nth-of-type({col_idx + 1})', "
                        f"{{opacity:0, x:-10}}, "
                        f"{{opacity:1, x:0, duration:0.3, ease:'power2.out'}}, {arrow_delay:.3f});"
                    )
        elif frame_style == "infographic":
            # Animate stats first, then items
            for idx in range(4):
                stat_delay = start + 0.6 + idx * 0.15
                gsap_anim_chains.append(
                    f"  tl.fromTo('#panel-{sid} .infographic-stat:nth-child({idx + 1})', "
                    f"{{opacity:0, y:15}}, "
                    f"{{opacity:1, y:0, duration:0.4, ease:'power2.out'}}, {stat_delay:.3f});"
                )
            for idx in range(4):
                item_delay = start + 1.2 + idx * 0.12
                gsap_anim_chains.append(
                    f"  tl.fromTo('#panel-{sid} .infographic-item:nth-child({idx + 1})', "
                    f"{{opacity:0, y:10}}, "
                    f"{{opacity:1, y:0, duration:0.3, ease:'power2.out'}}, {item_delay:.3f});"
                )
        elif frame_style == "venn_diagram":
            for idx in range(3):
                delay = start + 0.5 + idx * 0.3
                gsap_anim_chains.append(
                    f"  tl.fromTo('#venn-{sid}-{idx}', "
                    f"{{opacity:0, scale:0.5}}, "
                    f"{{opacity:1, scale:1, duration:0.6, ease:'back.out(1.4)'}}, {delay:.3f});"
                )
                gsap_anim_chains.append(
                    f"  tl.fromTo('#venn-label-{sid}-{idx}', "
                    f"{{opacity:0, y:10}}, "
                    f"{{opacity:1, y:0, duration:0.4, ease:'power2.out'}}, {delay + 0.2:.3f});"
                )
        elif frame_style == "pyramid":
            narration = scene.get("narration", "")
            levels = _parse_pyramid_items(narration)
            for idx in range(len(levels)):
                delay = start + 0.5 + idx * 0.2
                gsap_anim_chains.append(
                    f"  tl.fromTo('#pyramid-{sid}-{idx}', "
                    f"{{opacity:0, scaleX:0.8}}, "
                    f"{{opacity:1, scaleX:1, duration:0.5, ease:'back.out(1.7)'}}, {delay:.3f});"
                )
        elif frame_style == "cycle_diagram":
            narration = scene.get("narration", "")
            steps = _parse_cycle_items(narration)
            for idx in range(len(steps)):
                delay = start + 0.5 + idx * 0.25
                gsap_anim_chains.append(
                    f"  tl.fromTo('#cycle-node-{sid}-{idx}', "
                    f"{{opacity:0, scale:0}}, "
                    f"{{opacity:1, scale:1, duration:0.4, ease:'elastic.out(1, 0.5)'}}, {delay:.3f});"
                )
                if idx < len(steps) - 1:
                    gsap_anim_chains.append(
                        f"  tl.fromTo('#cycle-arrow-{sid}-{idx}', "
                        f"{{opacity:0}}, "
                        f"{{opacity:1, duration:0.2, ease:'power2.out'}}, {delay + 0.15:.3f});"
                    )
                gsap_anim_chains.append(
                    f"  tl.fromTo('#cycle-label-{sid}-{idx}', "
                    f"{{opacity:0}}, "
                    f"{{opacity:1, duration:0.3, ease:'power2.out'}}, {delay + 0.1:.3f});"
                )
        elif frame_style == "funnel":
            narration = scene.get("narration", "")
            stages = _parse_funnel_items(narration)
            for idx in range(len(stages)):
                delay = start + 0.5 + idx * 0.2
                gsap_anim_chains.append(
                    f"  tl.fromTo('#funnel-{sid}-{idx}', "
                    f"{{opacity:0, scaleX:0.7}}, "
                    f"{{opacity:1, scaleX:1, duration:0.5, ease:'power3.out'}}, {delay:.3f});"
                )
        elif frame_style == "flowchart":
            narration = scene.get("narration", "")
            nodes = _parse_flowchart_items(narration)
            for idx in range(len(nodes)):
                delay = start + 0.5 + idx * 0.2
                gsap_anim_chains.append(
                    f"  tl.fromTo('#fc-{sid}-{idx}', "
                    f"{{opacity:0, scale:0.8}}, "
                    f"{{opacity:1, scale:1, duration:0.4, ease:'back.out(1.5)'}}, {delay:.3f});"
                )
                if idx < len(nodes) - 1:
                    gsap_anim_chains.append(
                        f"  tl.fromTo('#fc-arrow-{sid}-{idx}', "
                        f"{{opacity:0, x:-8}}, "
                        f"{{opacity:1, x:0, duration:0.2, ease:'power2.out'}}, {delay + 0.15:.3f});"
                    )
        elif frame_style == "pie_chart":
            narration = scene.get("narration", "")
            slices_data = _parse_pie_data(narration)
            for idx in range(len(slices_data)):
                delay = start + 0.5 + idx * 0.15
                gsap_anim_chains.append(
                    f"  tl.fromTo('#pie-{sid}-{idx}', "
                    f"{{opacity:0, scale:0.5}}, "
                    f"{{opacity:1, scale:1, duration:0.5, ease:'back.out(1.3)'}}, {delay:.3f});"
                )
                gsap_anim_chains.append(
                    f"  tl.fromTo('#pie-legend-{sid}-{idx}', "
                    f"{{opacity:0, x:10}}, "
                    f"{{opacity:1, x:0, duration:0.3, ease:'power2.out'}}, {delay + 0.1:.3f});"
                )
        elif frame_style == "bar_chart":
            narration = scene.get("narration", "")
            bars_data = _parse_bar_data(narration)
            for idx in range(len(bars_data)):
                delay = start + 0.5 + idx * 0.12
                gsap_anim_chains.append(
                    f"  tl.fromTo('#bar-{sid}-{idx}', "
                    f"{{opacity:0, y:20}}, "
                    f"{{opacity:1, y:0, duration:0.4, ease:'power2.out'}}, {delay:.3f});"
                )
        elif frame_style == "annotated_diagram":
            narration = scene.get("narration", "")
            annotations = _parse_annotation_items(narration)
            for idx in range(len(annotations)):
                delay = start + 0.6 + idx * 0.2
                gsap_anim_chains.append(
                    f"  tl.fromTo('#ann-{sid}-{idx}', "
                    f"{{opacity:0, x:15}}, "
                    f"{{opacity:1, x:0, duration:0.4, ease:'power2.out'}}, {delay:.3f});"
                )

        # Exit animations (except last scene)
        if not is_last:
            fade_out_at = start + dur - 0.5
            gsap_anim_chains.append(
                f"  tl.to('#panel-{sid} .left-col', "
                f"{{opacity:0, x:-40, duration:0.4, ease:'power2.in'}}, {fade_out_at:.3f});"
            )
            gsap_anim_chains.append(
                f"  tl.to('#title-{sid}', "
                f"{{opacity:0, clipPath:'inset(0 0 0 100%)', duration:0.35, ease:'power2.in'}}, {fade_out_at:.3f});"
            )
            gsap_anim_chains.append(
                f"  tl.to('#body-{sid}', "
                f"{{opacity:0, y:-15, duration:0.3, ease:'power2.in'}}, {fade_out_at + 0.05:.3f});"
            )

            # Transition flash: subtle colored pulse
            trans_start = start + dur - CROSSFADE_S
            gsap_anim_chains.append(
                f"  tl.fromTo('#trans-{sid} .trans-flash', "
                f"{{opacity:0}}, "
                f"{{opacity:1, duration:{CROSSFADE_S:.2f}, ease:'power2.in'}}, {trans_start:.3f});"
            )
            gsap_anim_chains.append(
                f"  tl.to('#trans-{sid} .trans-flash', "
                f"{{opacity:0, duration:{CROSSFADE_S:.2f}, ease:'power2.out'}}, {trans_start + CROSSFADE_S:.3f});"
            )
    gsap_block = "\n".join(gsap_anim_chains)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width={WIDTH}, height={HEIGHT}, initial-scale=1" />
  <title>{_html_escape(manifest.get('document_title', 'VisualNote Video'))}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>{css}</style>
</head>
<body>
  <div id="root" data-composition-id="{COMPOSITION_ID}" data-start="0" data-width="{WIDTH}" data-height="{HEIGHT}">
{chr(10).join(layers)}
  </div>
  <script>
    (function() {{
      // Register a paused GSAP timeline on window.__timelines keyed by the
      // composition id. HyperFrames seeks this on every hf-seek event.
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
{gsap_block}
      window.__timelines["{COMPOSITION_ID}"] = tl;
    }})();
  </script>
</body>
</html>
"""
    return html, total_duration


# ---------------------------------------------------------------------------
# Project skeleton (so `hyperframes` recognizes the directory as a project)
# ---------------------------------------------------------------------------


def _build_package_json(project_dir: Path) -> Path:
    pkg_path = project_dir / "package.json"
    pkg = {
        "name": "visualnote-hyperframes",
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "description": "VisualNote composition for HyperFrames",
        "scripts": {
            "render": "npx --yes hyperframes@0.6.69 render",
        },
    }
    pkg_path.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    return pkg_path


def _build_hyperframes_config(project_dir: Path) -> Path:
    cfg_path = project_dir / "hyperframes.json"
    cfg = {
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
        "paths": {
            "blocks": "compositions",
            "components": "compositions/components",
            "assets": "assets",
        },
    }
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg_path


def _build_meta_json(project_dir: Path, doc_title: str) -> Path:
    import datetime as _dt
    meta_path = project_dir / "meta.json"
    meta = {
        "id": "visualnote-deep",
        "name": doc_title or "VisualNote Deep Dive",
        "createdAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta_path


# ---------------------------------------------------------------------------
# GPU / NVENC probe (reused pattern from pipeline/assembler.py)
# ---------------------------------------------------------------------------


def _probe_nvenc() -> bool:
    """Return True if the ffmpeg binary exposes h264_nvenc."""
    ffmpeg = CONFIG.ffmpeg_path or "ffmpeg"
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as exc:
        log.warning("ffmpeg probe failed: %s", exc)
        return False
    return bool(re.search(r"^\s*V[\.\s\S]*h264_nvenc", out.stdout, re.MULTILINE))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_with_hyperframes(
    manifest: dict,
    output_path: Path,
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
    fps: int = FPS,
    quality: str = "standard",
    crf: int = 26,
    workers: int = 4,
    use_gpu: Optional[bool] = None,
    page_side_compositing: bool = True,
    timeout_s: int = 3600,
) -> Path:
    """Render the manifest into a single MP4 using HyperFrames.

    Steps:
      1. Build a complete HyperFrames index.html with class="clip" divs,
         a paused GSAP timeline on window.__timelines, and per-scene
         <audio data-track-index> tracks.
      2. Invoke `npx hyperframes render` in the project directory. The
         engine handles audio mux natively — no post-render ffmpeg pass.
    """
    # Safety net: ensure every scene has a frame_style
    from deep_manifest import _assign_frame_styles
    manifest = _assign_frame_styles(manifest)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    project_dir = CONFIG.output_dir / "hyperframes_project"
    project_dir.mkdir(parents=True, exist_ok=True)

    _build_package_json(project_dir)
    _build_hyperframes_config(project_dir)
    _build_meta_json(project_dir, manifest.get("document_title", "VisualNote Deep Dive"))

    index_html_path = project_dir / "index.html"
    html, total_duration = _build_composition_html(manifest, project_dir)
    index_html_path.write_text(html, encoding="utf-8")

    if use_gpu is None:
        use_gpu = _probe_nvenc()
        log.info("GPU probe: h264_nvenc available=%s", use_gpu)

    npx = shutil.which("npx") or "npx"
    resolution_preset = (
        "landscape" if width >= height and height <= 1080
        else "landscape-4k" if width >= height and height > 1080
        else "portrait" if width < height and width <= 1080
        else "portrait-4k"
    )
    cmd = [
        npx, "--yes", "hyperframes", "render",
        str(project_dir),
        "-o", str(output_path),
        "-f", str(fps),
        "-q", quality,
        "--crf", str(crf),
        "--resolution", resolution_preset,
        "--workers", str(workers),
    ]
    if use_gpu:
        cmd.append("--gpu")
    if page_side_compositing:
        cmd.append("--page-side-compositing")

    log.info("Running: %s", " ".join(cmd))
    log.info(
        "Composition: %d scenes, %.1fs total, gpu=%s",
        len(manifest.get("scenes", [])),
        total_duration,
        use_gpu,
    )

    proc = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"hyperframes render failed (rc={proc.returncode}): {stderr[-3000:]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(
            f"hyperframes render produced no output at {output_path}"
        )

    log.info(
        "Final video: %s (%.1f MB)",
        output_path,
        output_path.stat().st_size / 1e6,
    )
    return output_path


__all__ = ["render_with_hyperframes"]
