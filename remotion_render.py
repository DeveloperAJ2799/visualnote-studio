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
# IGWANI spec: visual concepts only, no bullet lists
_FRAME_STYLE_TO_TEMPLATE: Dict[str, str] = {
    # title variants
    "title_hero": "title_intro",
    "chapter_marker": "title_intro",
    # diagram / flow variants
    "diagram_center": "concept_diagram",
    "flow_chain": "process_flow",
    "steps_horizontal": "process_flow",
    "process_flow": "process_flow",
    "flowchart": "process_flow",
    "infographic": "concept_diagram",
    "annotated_diagram": "concept_diagram",
    # comparison
    "split_compare": "comparison_visual",
    "listing_columns": "comparison_visual",
    "type_columns": "comparison_visual",
    # quote
    "quote_callout": "quote_highlight",
    # data viz
    "venn_diagram": "concept_diagram",
    "pyramid": "process_flow",
    "cycle_diagram": "process_flow",
    "funnel": "process_flow",
    "pie_chart": "concept_diagram",
    "bar_chart": "concept_diagram",
    # stats
    "stats_grid": "stat_beat",
}

# Keyword-based template assignment (used when no frame_style is set)
# IGWANI spec: visual concepts only, no bullet lists
_KEYWORD_TEMPLATE: list[tuple[list[str], str]] = [
    (["vs", "versus", "comparison", "compare", "difference"], "comparison_visual"),
    (["step", "process", "sequence", "workflow", "first", "then", "finally"], "process_flow"),
    (["quote", "takeaway", "key insight", "remember"], "quote_highlight"),
    (["diagram", "structure", "components", "parts", "anatomy"], "concept_diagram"),
    (["cycle", "flow", "chain", "cycle"], "process_flow"),
]

# Annotation types for auto-generation
_ANNOTATION_KEYWORDS: Dict[str, List[str]] = {
    "circle": ["number", "percent", "stat", "result", "accuracy"],
    "underline": ["important", "key", "critical", "essential", "note", "remember"],
    "arrow": ["leads to", "results in", "creates", "produces", "generates"],
}


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

    return "concept_diagram"


def _build_fields(scene: Dict[str, Any], template: str) -> Dict[str, Any]:
    """Extract the ``fields`` dict for a given template from the scene data.
    
    IGWANI spec: visual concepts only, no bullet lists.
    """
    title = scene.get("title", "")
    narration = scene.get("narration", "")

    if template == "title_intro":
        return {"title": title, "subtitle": narration[:80] if len(narration) > 80 else ""}

    if template == "concept_diagram":
        # Create a simple diagram from the narration
        return {
            "title": title,
            "nodes": [
                {"x": 960, "y": 400, "label": title.split(":")[0] if ":" in title else title[:20], "sublabel": "Concept", "enterFrame": 20, "shape": "circle", "size": 180}
            ],
            "connectors": []
        }

    if template == "process_flow":
        # Create a process flow from the narration
        steps = _narration_to_visual_steps(narration)
        return {"title": title, "steps": steps}

    if template == "comparison_visual":
        # Create a comparison from the narration
        return {
            "title": title,
            "leftLabel": "Option A",
            "rightLabel": "Option B",
            "leftItems": [{"label": "Feature 1"}, {"label": "Feature 2"}],
            "rightItems": [{"label": "Feature 1"}, {"label": "Feature 2"}]
        }

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


def _narration_to_visual_steps(text: str) -> List[Dict[str, Any]]:
    """Convert narration into visual steps for process flow.
    
    IGWANI spec: visual concepts only, no bullet lists.
    Returns step objects with x/y positions for diagram layout.
    """
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    if not sentences:
        return [{"label": "Step 1", "sublabel": "Process", "x": 200, "y": 440, "enterFrame": 20}]
    
    steps = []
    num_steps = min(len(sentences), 5)
    x_positions = [200, 520, 840, 1160, 1480]
    
    for i in range(num_steps):
        # Extract key phrase from sentence (first few words)
        words = sentences[i].split()[:3]
        label = " ".join(words) if words else f"Step {i + 1}"
        steps.append({
            "label": label,
            "sublabel": f"Step {i + 1}",
            "x": x_positions[i] if i < len(x_positions) else 200 + i * 320,
            "y": 440,
            "enterFrame": 20 + i * 30
        })
    return steps


def _extract_annotations(scene: Dict[str, Any], duration_frames: int) -> List[Dict[str, Any]]:
    """Extract annotations from scene manifest, or generate auto-annotations.

    Priority:
    1. Manual annotations from scene.annotations (if present)
    2. Auto-generated annotations from narration text
    """
    # Check for manual annotations in manifest
    if scene.get("annotations"):
        manual = scene["annotations"]
        if isinstance(manual, list) and len(manual) > 0:
            # Validate and normalize manual annotations
            validated = []
            for ann in manual:
                if isinstance(ann, dict) and "type" in ann and "startFrame" in ann:
                    validated.append({
                        "type": ann["type"],
                        "target": ann.get("target", ""),
                        "startFrame": ann["startFrame"],
                        "duration": ann.get("duration", 20),
                        "color": ann.get("color"),
                    })
            if validated:
                return validated

    # Auto-generate annotations from narration
    narration = scene.get("narration", "")
    if len(narration.split()) < 20:
        return []  # Too short for annotations

    annotations = []
    words = narration.split()
    total_words = len(words)

    # Find emphasis keywords
    for ann_type, keywords in _ANNOTATION_KEYWORDS.items():
        if len(annotations) >= 2:  # Max 2 annotations per scene
            break

        for i, word in enumerate(words):
            if len(annotations) >= 2:
                break

            word_lower = word.lower().strip(".,;:!?")
            if word_lower in keywords:
                # Convert word position to frame timing
                word_ratio = i / total_words
                start_frame = int(word_ratio * duration_frames * 0.8) + 15
                start_frame = min(start_frame, duration_frames - 30)

                annotations.append({
                    "type": ann_type,
                    "target": word,
                    "startFrame": start_frame,
                    "duration": 20,
                    "color": None,  # Use default (amber)
                })
                break  # One per type

    return annotations


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

    # Extract annotations (manual or auto-generated)
    annotations = _extract_annotations(scene, duration_frames)

    return {
        "scene_id": scene_id,
        "template": template,
        "narration": scene.get("narration", ""),
        "fields": fields,
        "durationInFrames": duration_frames,
        "annotations": annotations,
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
