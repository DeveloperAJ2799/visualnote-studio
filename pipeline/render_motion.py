"""Dynamic Motion Graphics Renderer

Writes LLM-generated Remotion JSX to scene files and renders the video.
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
from pipeline.asset_generator import generate_scene_assets
from pipeline.motion_gen import generate_motion_scenes
from pipeline.scene_planner import plan_scenes

log = logging.getLogger(__name__)

REMOTION_PROJECT = CONFIG.remotion_project_dir
SCENES_DIR = REMOTION_PROJECT / "src" / "scenes"
FPS = 30


def _write_scene_file(scene_name: str, code: str) -> Path:
    """Write a scene component to the scenes directory."""
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    
    scene_path = SCENES_DIR / f"{scene_name}.tsx"
    scene_path.write_text(code, encoding="utf-8")
    
    log.info("Wrote scene file: %s", scene_path)
    return scene_path


def _generate_imports(scenes: List[Dict[str, Any]]) -> str:
    """Generate import statements for all scenes."""
    imports = []
    for i, scene in enumerate(scenes):
        name = scene.get("scene_name", f"Scene{i+1:03d}")
        imports.append(f'import {name} from "./scenes/{name}";')
    return "\n".join(imports)


def _generate_switch_cases(scenes: List[Dict[str, Any]]) -> str:
    """Generate switch cases for scene selection."""
    cases = []
    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", i + 1)
        name = scene.get("scene_name", f"Scene{i+1:03d}")
        cases.append(f'    case {scene_id}: return <{name} />;')
    return "\n".join(cases)


def _update_course_reel(scenes: List[Dict[str, Any]]) -> None:
    """Update CourseReel.tsx with dynamic scene imports."""
    imports = _generate_imports(scenes)
    cases = _generate_switch_cases(scenes)
    
    course_reel_code = f'''import React from "react";
import {{ AbsoluteFill, Sequence, staticFile }} from "remotion";
import {{ Audio }} from "@remotion/media";
import {{ GrainOverlay }} from "./components/GrainOverlay";
import {{ SceneTransition }} from "./components/SceneTransition";
{imports}
import type {{ CourseReelProps, Scene }} from "./types";

function renderScene(scene: Scene): React.ReactNode {{
  switch (scene.scene_id) {{
{cases}
    default: return <div />;
  }}
}}

export const CourseReel: React.FC<CourseReelProps> = ({{ scenes }}) => {{
  let fromFrame = 0;
  return (
    <AbsoluteFill>
      {{scenes.map((scene) => {{
        const start = fromFrame;
        fromFrame += scene.durationInFrames;
        return (
          <Sequence key={{scene.scene_id}} from={{start}} durationInFrames={{scene.durationInFrames}}>
            <Audio src={{staticFile(`scenes/scene_${{String(scene.scene_id).padStart(3, "0")}}_audio.wav`)}} />
            <SceneTransition durationInFrames={{scene.durationInFrames}}>
              {{renderScene(scene)}}
            </SceneTransition>
          </Sequence>
        );
      }})}}
      <GrainOverlay />
    </AbsoluteFill>
  );
}};
'''
    
    course_reel_path = REMOTION_PROJECT / "src" / "CourseReel.tsx"
    course_reel_path.write_text(course_reel_code, encoding="utf-8")
    log.info("Updated CourseReel.tsx with %d scenes", len(scenes))


def _update_remotion_props(scenes: List[Dict[str, Any]], audio_durations: Dict[int, float]) -> Path:
    """Update remotion_props.json with scene data."""
    props_scenes = []
    
    for scene in scenes:
        scene_id = scene["scene_id"]
        duration_s = audio_durations.get(scene_id, scene.get("metadata", {}).get("duration_frames", 180) / FPS)
        duration_frames = math.ceil(duration_s * FPS)
        
        props_scenes.append({
            "scene_id": scene_id,
            "template": "dynamic",
            "narration": scene.get("metadata", {}).get("narration", ""),
            "fields": {},
            "durationInFrames": duration_frames,
            "annotations": [],
        })
    
    props = {
        "course_title": "Generated Motion Graphics",
        "fps": FPS,
        "scenes": props_scenes,
    }
    
    props_path = CONFIG.output_dir / "remotion_props_motion.json"
    props_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f, indent=2)
    
    log.info("Wrote Remotion props: %s", props_path)
    return props_path


def _copy_audio_files(scenes: List[Dict[str, Any]]) -> Dict[int, float]:
    """Copy WAV files to Remotion public directory and return durations."""
    remotion_public = REMOTION_PROJECT / "public"
    remotion_scenes_dir = remotion_public / "scenes"
    remotion_scenes_dir.mkdir(parents=True, exist_ok=True)
    
    durations = {}
    
    for scene in scenes:
        scene_id = scene["scene_id"]
        src = CONFIG.scenes_dir / f"scene_{scene_id:03d}_audio.wav"
        dst = remotion_scenes_dir / f"scene_{scene_id:03d}_audio.wav"
        
        if src.exists():
            shutil.copy2(src, dst)
            # Get duration
            try:
                from pipeline.tts import _probe_wav_duration
                durations[scene_id] = _probe_wav_duration(src)
            except Exception:
                durations[scene_id] = 6.0
            log.info("Copied audio for scene %d", scene_id)
        else:
            log.warning("No audio file for scene %d", scene_id)
            durations[scene_id] = 6.0
    
    return durations


def render_motion_graphics(
    manifest: Dict[str, Any],
    output_path: Path,
    *,
    quality: str = "standard",
) -> Path:
    """Render video using LLM-generated motion graphics.

    1. Generates infographic assets via NIM API
    2. Generates Remotion + Three.js code for each scene via LLM
    3. Writes scene files to Remotion project
    4. Updates CourseReel.tsx with dynamic imports
    5. Renders the final video

    Args:
        manifest: Scene manifest with narration text
        output_path: Output MP4 path
        quality: Rendering quality (not used yet)

    Returns:
        Path to rendered video
    """
    scenes = manifest.get("scenes", [])
    course_title = manifest.get("document_title", "Generated Course")

    log.info("Generating motion graphics for %d scenes", len(scenes))

    # Step 1: Generate infographic assets via NIM API
    log.info("Generating infographic assets...")
    asset_map = {}
    try:
        asset_map = generate_scene_assets(scenes)
        log.info("Generated %d assets", len(asset_map))
    except Exception as e:
        log.warning("Asset generation failed (continuing without assets): %s", e)

    # Step 2: Generate motion graphics code
    generated = generate_motion_scenes(
        scenes=scenes,
        course_context=f"Course: {course_title}",
        asset_map=asset_map,
    )
    
    # Filter to valid scenes
    valid_scenes = [s for s in generated if s["validation"]["valid"]]
    failed_scenes = [s for s in generated if not s["validation"]["valid"]]
    
    if failed_scenes:
        log.warning("Failed to generate %d scenes:", len(failed_scenes))
        for s in failed_scenes:
            log.warning("  Scene %d: %s", s["scene_id"], s["validation"]["errors"])
    
    if not valid_scenes:
        raise RuntimeError("No valid scenes generated")
    
    # Write scene files
    for scene in valid_scenes:
        _write_scene_file(scene["scene_name"], scene["code"])
    
    # Copy audio and get durations
    audio_durations = _copy_audio_files(valid_scenes)
    
    # Update CourseReel.tsx
    _update_course_reel(valid_scenes)
    
    # Update props
    props_path = _update_remotion_props(valid_scenes, audio_durations)
    
    # Render
    npx = shutil.which("npx")
    if not npx:
        raise FileNotFoundError("npx not found")
    
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
    
    log.info("Running: %s", " ".join(cmd))

    # Set temp dirs to D: drive to avoid C: drive space issues
    import os
    render_env = os.environ.copy()
    render_env["TEMP"] = "D:\\tagmango\\temp"
    render_env["TMP"] = "D:\\tagmango\\temp"
    render_env["TMPDIR"] = "D:\\tagmango\\temp"

    proc = subprocess.run(
        cmd,
        cwd=str(REMOTION_PROJECT),
        capture_output=True,
        text=True,
        timeout=3600,
        env=render_env,
    )
    
    if proc.returncode != 0:
        log.error("Render failed (code %d)", proc.returncode)
        log.error("stderr: %s", proc.stderr[-2000:] if proc.stderr else "")
        raise RuntimeError(f"Render failed: {proc.stderr[-500:] if proc.stderr else 'unknown'}")
    
    log.info("Render complete: %s", output_path)
    return output_path


def render_from_narration(
    narration: str,
    output_path: Path,
    course_context: str = "",
    target_duration_s: float = 180.0,
) -> Path:
    """Full pipeline: narration text → scene plan → LLM code → render.

    Steps:
    1. Plan scenes from narration (narration → visual_concept JSON)
    2. Generate Remotion code for each scene via LLM
    3. Write scene files and render

    Args:
        narration: Full narration text for the video
        output_path: Output MP4 path
        course_context: Course title, module info
        target_duration_s: Target total duration

    Returns:
        Path to rendered video
    """
    log.info("=== Full Pipeline: Narration → Video ===")
    log.info("Narration length: %d chars", len(narration))
    log.info("Target duration: %.0fs", target_duration_s)

    # Step 1: Plan scenes
    log.info("--- Step 1: Planning scenes ---")
    plan = plan_scenes(
        narration=narration,
        course_context=course_context,
        target_duration_s=target_duration_s,
    )

    if not plan["validation"]["valid"]:
        log.error("Scene plan validation failed: %s", plan["validation"]["errors"])
        raise RuntimeError(f"Scene plan failed: {plan['validation']['errors']}")

    if plan["validation"]["warnings"]:
        for w in plan["validation"]["warnings"]:
            log.warning("Scene plan warning: %s", w)

    scenes = plan["scenes"]
    log.info("Planned %d scenes (total %.0fs)", len(scenes),
             plan["metadata"].get("total_planned_duration_s", 0))

    # Step 2: Generate infographic assets
    log.info("--- Step 2: Generating infographic assets ---")
    asset_map = {}
    try:
        asset_map = generate_scene_assets(scenes)
        log.info("Generated %d assets", len(asset_map))
    except Exception as e:
        log.warning("Asset generation failed (continuing without assets): %s", e)

    # Step 3: Generate motion code
    log.info("--- Step 3: Generating 3D motion graphics code ---")
    generated = generate_motion_scenes(
        scenes=scenes,
        course_context=course_context,
        asset_map=asset_map,
    )

    # Filter valid scenes
    valid_scenes = [s for s in generated if s["validation"]["valid"]]
    if not valid_scenes:
        raise RuntimeError("No valid scenes generated")

    log.info("Generated %d/%d valid scenes", len(valid_scenes), len(generated))

    # Step 4: Write files and render
    log.info("--- Step 4: Writing scene files and rendering ---")
    for scene in valid_scenes:
        _write_scene_file(scene["scene_name"], scene["code"])

    audio_durations = _copy_audio_files(valid_scenes)
    _update_course_reel(valid_scenes)
    props_path = _update_remotion_props(valid_scenes, audio_durations)

    # Render
    npx = shutil.which("npx")
    if not npx:
        raise FileNotFoundError("npx not found")

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        npx, "remotion", "render",
        "src/index.ts", "CourseReel", str(output_path),
        f"--props={props_path}",
        "--codec=h264", "--overwrite",
    ]

    log.info("Running: %s", " ".join(cmd))

    # Set temp dirs to D: drive to avoid C: drive space issues
    import os
    render_env = os.environ.copy()
    render_env["TEMP"] = "D:\\tagmango\\temp"
    render_env["TMP"] = "D:\\tagmango\\temp"
    render_env["TMPDIR"] = "D:\\tagmango\\temp"

    proc = subprocess.run(
        cmd,
        cwd=str(REMOTION_PROJECT),
        capture_output=True, text=True, timeout=3600,
        env=render_env,
    )

    if proc.returncode != 0:
        log.error("Render failed (code %d)", proc.returncode)
        log.error("stderr: %s", proc.stderr[-2000:] if proc.stderr else "")
        raise RuntimeError(f"Render failed: {proc.stderr[-500:] if proc.stderr else 'unknown'}")

    log.info("=== Pipeline Complete: %s ===", output_path)
    return output_path
