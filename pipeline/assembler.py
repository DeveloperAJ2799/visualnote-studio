"""Video assembly: concat scene clips with audio and crossfades, then FFmpeg re-encode.

Pipeline:
  1. For each scene, locate the visual file (`scene_{id}.mp4` or `scene_{id}.png`)
     and the audio file (`scene_{id}_audio.wav`).
  2. Build a `VideoClip` per scene; if the visual is a PNG, use `ImageClip`
     with duration = audio duration. If the visual is an MP4, extend its
     duration to match the audio (per FR-06: never cut narration).
  3. Apply 0.3s visual crossfade in/out on every clip (except first has no
     fade-in, last has no fade-out).
  4. `concatenate_videoclips` with `method="compose"`, then attach audio.
  5. Write the result to a temp MP4 (moviepy + libx264 ultrafast).
  6. Re-encode the temp with FFmpeg using NVENC if available, else libx264.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    VideoClip,
    VideoFileClip,
    concatenate_videoclips,
)

from config import CONFIG

log = logging.getLogger(__name__)

CROSSFADE_S = 0.3
TARGET_FPS = 30
TARGET_SIZE = (1920, 1080)
PIX_FMT = "yuv420p"
TEMP_BASENAME = "visualnote_intermediate.mp4"


def _probe_nvenc() -> bool:
    """Return True if the bundled ffmpeg has an h264_nvenc encoder."""
    try:
        out = subprocess.run(
            [CONFIG.ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as exc:
        log.warning("ffmpeg probe failed: %s", exc)
        return False
    return bool(re.search(r"^\s*V[\.\s\S]*h264_nvenc", out.stdout, re.MULTILINE))


def _find_visual(scene_id: int) -> Path:
    """Return the existing visual path for a scene, preferring mp4 over png."""
    mp4 = CONFIG.scenes_dir / f"scene_{scene_id:03d}.mp4"
    if mp4.exists():
        return mp4
    png = CONFIG.scenes_dir / f"scene_{scene_id:03d}.png"
    if png.exists():
        return png
    raise FileNotFoundError(
        f"No visual file for scene {scene_id} (looked for {mp4.name} and {png.name})"
    )


def _find_audio(scene_id: int) -> Path:
    wav = CONFIG.scenes_dir / f"scene_{scene_id:03d}_audio.wav"
    if not wav.exists():
        raise FileNotFoundError(f"No audio file for scene {scene_id} (looked for {wav.name})")
    return wav


def _build_scene_clip(
    visual_path: Path,
    audio_path: Path,
    *,
    is_first: bool,
    is_last: bool,
) -> VideoClip:
    """Build a single video clip with synced audio and 0.3s crossfades."""
    audio_clip = AudioFileClip(str(audio_path))
    if visual_path.suffix.lower() == ".mp4":
        clip = VideoFileClip(str(visual_path))
        # Pad to audio duration if needed (FR-06: never cut narration).
        clip = clip.set_duration(max(clip.duration, audio_clip.duration))
    else:
        # Static image held for the audio duration.
        clip = ImageClip(str(visual_path)).set_duration(audio_clip.duration)

    clip = clip.resize(newsize=TARGET_SIZE)
    if not is_first:
        clip = clip.crossfadein(CROSSFADE_S)
    if not is_last:
        clip = clip.crossfadeout(CROSSFADE_S)
    return clip.set_audio(audio_clip)


def _build_final_clip(manifest: dict) -> Tuple[VideoClip, List[Path]]:
    """Build the concatenated VideoClip from all scenes. Returns (clip, temp_paths)."""
    scenes = manifest.get("scenes", [])
    if not scenes:
        raise ValueError("Manifest has no scenes to assemble.")
    temp_paths: List[Path] = []
    clips: List[VideoClip] = []
    for i, scene in enumerate(scenes):
        scene_id = scene["scene_id"]
        visual = _find_visual(scene_id)
        audio = _find_audio(scene_id)
        is_first = i == 0
        is_last = i == len(scenes) - 1
        clip = _build_scene_clip(
            visual, audio, is_first=is_first, is_last=is_last
        )
        clips.append(clip)
    final = concatenate_videoclips(clips, method="compose", padding=0)
    return final, temp_paths


def _ffmpeg_final_encode(
    intermediate: Path,
    output: Path,
    *,
    use_nvenc: bool,
) -> Path:
    """Re-encode `intermediate` to `output` with NVENC if available."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if use_nvenc:
        v_codec = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
    else:
        v_codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    cmd = [
        CONFIG.ffmpeg_path, "-y",
        "-i", str(intermediate),
        "-r", str(TARGET_FPS),
        "-vf", f"scale={TARGET_SIZE[0]}:{TARGET_SIZE[1]}:force_original_aspect_ratio=decrease,pad={TARGET_SIZE[0]}:{TARGET_SIZE[1]}:(ow-iw)/2:(oh-ih)/2",
        "-pix_fmt", PIX_FMT,
        *v_codec,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ]
    log.info("Final encode (nvenc=%s): %s", use_nvenc, " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg final encode failed (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout)[-2000:]}"
        )
    return output


def assemble(manifest: dict, output_path: Path) -> Path:
    """Build the final MP4 from a manifest and its on-disk scene assets."""
    output_path = Path(output_path)
    log.info("Assembling %d scenes into %s", len(manifest["scenes"]), output_path)

    final_clip, _ = _build_final_clip(manifest)

    with tempfile.TemporaryDirectory(prefix="visualnote_assemble_") as tmp:
        intermediate = Path(tmp) / TEMP_BASENAME
        try:
            log.info("Writing intermediate MP4 to %s", intermediate)
            final_clip.write_videofile(
                str(intermediate),
                fps=TARGET_FPS,
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",
                threads=4,
                logger=None,
            )
        finally:
            final_clip.close()

        if not intermediate.exists() or intermediate.stat().st_size == 0:
            raise RuntimeError("moviepy did not produce an intermediate file")

        use_nvenc = _probe_nvenc()
        if not use_nvenc:
            log.warning(
                "h264_nvenc not available; falling back to libx264. "
                "Check NVIDIA driver / FFmpeg build for hardware acceleration."
            )
        _ffmpeg_final_encode(intermediate, output_path, use_nvenc=use_nvenc)

    log.info("Final video: %s (%.1f MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path
