"""Remotion renderer.

Converts a VisualNote scene manifest into a Remotion props JSON and invokes
``npx remotion render`` to produce the final MP4. The Remotion project lives
in ``remotion_project/`` at the project root.

Usage from the orchestrator::

    from remotion_render import render_with_remotion
    render_with_remotion(manifest, output_path)
"""
from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from config import CONFIG

log = logging.getLogger(__name__)

REMOTION_PROJECT = CONFIG.project_root / "remotion_project"
FPS = 30

# Mapping: current frame_style → PRD template name
_FRAME_STYLE_TO_TEMPLATE: Dict[str, str] = {
    # title variants
    "title_hero": "title_intro",
    "chapter_marker": "title_intro",
    # text / list variants
    "text_only": "bullet_explainer",
    "listing_columns": "bullet_explainer",
    "stats_grid": "bullet_explainer",
    "type_columns": "bullet_explainer",
    # comparison
    "split_compare": "comparison_table",
    # process / flow variants
    "steps_horizontal": "step_process",
    "flow_chain": "step_process",
    "process_flow": "step_process",
    "flowchart": "step_process",
    # quote
    "quote_callout": "quote_highlight",
    # image / diagram variants → bullet_explainer with title
    "image_left": "bullet_explainer",
    "image_right": "bullet_explainer",
    "full_bleed": "bullet_explainer",
    "diagram_center": "bullet_explainer",
    "infographic": "bullet_explainer",
    "annotated_diagram": "bullet_explainer",
    # data viz fallback → bullet_explainer
    "venn_diagram": "bullet_explainer",
    "pyramid": "bullet_explainer",
    "cycle_diagram": "bullet_explainer",
    "funnel": "bullet_explainer",
    "pie_chart": "bullet_explainer",
    "bar_chart": "bullet_explainer",
}

# Keyword-based template assignment (used when no frame_style is set)
_KEYWORD_TEMPLATE: list[tuple[list[str], str]] = [
    (["vs", "versus", "comparison", "compare", "difference"], "comparison_table"),
    (["step", "process", "sequence", "workflow", "first", "then", "finally"], "step_process"),
    (["quote", "takeaway", "key insight", "remember"], "quote_highlight"),
    (["tool", "app", "site", "software", "platform"], "tool_showcase"),
    (["list", "items", "uses", "functions", "roles", "types", "categories"], "bullet_explainer"),
]


def _resolve_template(scene: Dict[str, Any], is_first: bool, is_last: bool) -> str:
    """Determine the Remotion template for a scene."""
    if is_last:
        return "closing_cta"
    if is_first:
        return "title_intro"

    # Use LLM-assigned template if present
    if scene.get("template") and scene["template"] in _FRAME_STYLE_TO_TEMPLATE.values():
        return scene["template"]

    # Map from frame_style if available
    style = scene.get("frame_style", "")
    if style in _FRAME_STYLE_TO_TEMPLATE:
        return _FRAME_STYLE_TO_TEMPLATE[style]

    # Keyword heuristics on narration + title
    text = f"{scene.get('title', '')} {scene.get('narration', '')}".lower()
    for keywords, tmpl in _KEYWORD_TEMPLATE:
        if any(kw in text for kw in keywords):
            return tmpl

    return "bullet_explainer"


def _build_fields(scene: Dict[str, Any], template: str) -> Dict[str, Any]:
    """Extract the ``fields`` dict for a given template from the scene data."""
    title = scene.get("title", "")
    narration = scene.get("narration", "")

    if template == "title_intro":
        return {"title": title, "subtitle": narration[:80] if len(narration) > 80 else ""}

    if template == "bullet_explainer":
        # Split narration into rough bullet points
        bullets = _narration_to_bullets(narration)
        return {"heading": title, "bullets": bullets}

    if template == "tool_showcase":
        return {
            "tool_name": title,
            "description": narration,
            "tool_logo_url": None,
            "link": None,
        }

    if template == "comparison_table":
        return {"columns": ["Option A", "Option B"], "rows": [[title, narration[:60]]]}

    if template == "step_process":
        steps = _narration_to_steps(narration)
        return {"steps": steps}

    if template == "quote_highlight":
        return {"quote_text": narration, "attribution": None}

    if template == "closing_cta":
        return {"heading": title, "cta_text": "Thank you for watching", "links": []}

    return {"title": title}


def _narration_to_bullets(text: str) -> List[str]:
    """Split narration text into bullet-point-sized chunks."""
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    if not sentences:
        return [text[:120]]
    # Group into chunks of ~2 sentences
    bullets: List[str] = []
    for i in range(0, len(sentences), 2):
        chunk = ". ".join(sentences[i : i + 2])
        if not chunk.endswith("."):
            chunk += "."
        bullets.append(chunk)
    return bullets[:6]


def _narration_to_steps(text: str) -> List[Dict[str, str]]:
    """Convert narration into numbered steps."""
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    if not sentences:
        return [{"label": "Step 1", "description": text[:80]}]
    steps = []
    for i, s in enumerate(sentences[:6]):
        steps.append({"label": f"Step {i + 1}", "description": s[:80]})
    return steps


def _scene_to_remotion(
    scene: Dict[str, Any],
    is_first: bool,
    is_last: bool,
    scenes_dir: Path,
) -> Dict[str, Any]:
    """Convert one manifest scene into a Remotion scene dict."""
    template = _resolve_template(scene, is_first, is_last)
    fields = _build_fields(scene, template)

    # Determine actual duration from TTS audio
    scene_id = scene["scene_id"]
    wav_path = scenes_dir / f"scene_{scene_id:03d}_audio.wav"
    if wav_path.exists():
        from pipeline.tts import _probe_wav_duration
        duration_s = _probe_wav_duration(wav_path)
    else:
        duration_s = scene.get("duration_hint_s", 15)

    duration_s = max(1.5, duration_s)
    duration_frames = math.ceil(duration_s * FPS)

    return {
        "scene_id": scene_id,
        "template": template,
        "narration": scene.get("narration", ""),
        "fields": fields,
        "durationInFrames": duration_frames,
    }


def _manifest_to_remotion_props(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a full VisualNote manifest into Remotion inputProps."""
    scenes = manifest.get("scenes", [])
    scenes_dir = CONFIG.scenes_dir

    remotion_scenes = []
    for i, scene in enumerate(scenes):
        remotion_scenes.append(
            _scene_to_remotion(
                scene,
                is_first=(i == 0),
                is_last=(i == len(scenes) - 1),
                scenes_dir=scenes_dir,
            )
        )

    total_frames = sum(s["durationInFrames"] for s in remotion_scenes)

    log.info(
        "Remotion props: %d scenes, %d total frames (%.1fs at %dfps)",
        len(remotion_scenes),
        total_frames,
        total_frames / FPS,
        FPS,
    )

    return {
        "course_title": manifest.get("document_title", "Untitled"),
        "fps": FPS,
        "scenes": remotion_scenes,
    }


def render_with_remotion(
    manifest: Dict[str, Any],
    output_path: Path,
    *,
    quality: str = "standard",
) -> Path:
    """Render the final video using Remotion.

    1. Converts the manifest to Remotion props.
    2. Writes props JSON to disk.
    3. Invokes ``npx remotion render`` in the Remotion project directory.
    4. Returns the output MP4 path.
    """
    if not REMOTION_PROJECT.exists():
        raise FileNotFoundError(
            f"Remotion project not found at {REMOTION_PROJECT}. "
            "Run 'npm install' in remotion_project/ first."
        )

    npx = shutil.which("npx")
    if not npx:
        raise FileNotFoundError("npx not found in PATH. Install Node.js first.")

    # Build props
    props = _manifest_to_remotion_props(manifest)
    props_path = CONFIG.output_dir / "remotion_props.json"
    props_path.parent.mkdir(parents=True, exist_ok=True)
    with open(props_path, "w", encoding="utf-8") as fh:
        json.dump(props, fh, ensure_ascii=False, indent=2)
    log.info("Wrote Remotion props: %s", props_path)

    # Copy audio files into Remotion public/ so staticFile() works
    remotion_public = REMOTION_PROJECT / "public"
    remotion_scenes_dir = remotion_public / "scenes"
    remotion_scenes_dir.mkdir(parents=True, exist_ok=True)
    _link_audio_files(CONFIG.scenes_dir, remotion_scenes_dir, manifest)

    # Build render command — ensure output_path is absolute so it resolves
    # correctly from the Remotion project's cwd.
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        npx,
        "remotion",
        "render",
        "src/index.ts",
        "CourseReel",
        str(output_path),
        f"--props={props_path}",
        "--codec=h264",
        "--overwrite",
    ]

    log.info("Remotion render: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(REMOTION_PROJECT),
        capture_output=True,
        text=True,
        timeout=3600,
    )

    if proc.returncode != 0:
        log.error("Remotion render failed (code %d)", proc.returncode)
        log.error("stderr: %s", proc.stderr[-2000:] if proc.stderr else "(empty)")
        raise RuntimeError(
            f"Remotion render failed (code {proc.returncode}): "
            f"{proc.stderr[-500:] if proc.stderr else 'unknown error'}"
        )

    log.info("Remotion render complete: %s", output_path)
    return output_path


def _link_audio_files(src_dir: Path, dst_dir: Path, manifest: Dict[str, Any]) -> None:
    """Copy WAV files into the Remotion public directory."""
    import shutil as _shutil

    for scene in manifest.get("scenes", []):
        scene_id = scene["scene_id"]
        src = src_dir / f"scene_{scene_id:03d}_audio.wav"
        dst = dst_dir / f"scene_{scene_id:03d}_audio.wav"
        if src.exists() and not dst.exists():
            _shutil.copy2(src, dst)
