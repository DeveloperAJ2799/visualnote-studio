"""Manim scene generation and rendering.

For each scene in the manifest with `visual_type: manim_animation`:
  1. Ask the MiMoClient for a ManimCE Python script.
  2. Write it to a temp file.
  3. Invoke `manim -qh` via subprocess with a timeout.
  4. On failure, retry up to N times with the previous error fed back to the LLM.
  5. On final failure, return a Pillow title-card PNG path as a graceful fallback.

The returned path is always a usable visual file: an `.mp4` on success, a `.png`
on fallback. The assembler can consume either form.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from config import CONFIG
from pipeline.clients.base import MiMoClient

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 60
DEFAULT_MAX_ATTEMPTS = 3


def _make_title_card_png(
    title: str,
    subtitle: str,
    out_path: Path,
    *,
    size: Tuple[int, int] = (1920, 1080),
    bg: str = "#1a1a2e",
    accent: str = "#4fc3f7",
) -> Path:
    """Render a simple title card to PNG using Pillow."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("arial.ttf", 72)
        sub_font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()

    def _centered(text: str, font: ImageFont.ImageFont, y: int, color: str) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        x = (size[0] - w) // 2
        draw.text((x, y), text, font=font, fill=color)

    _centered(title, title_font, int(size[1] * 0.40), "#ffffff")
    if subtitle:
        _centered(subtitle, sub_font, int(size[1] * 0.55), accent)
    img.save(out_path, "PNG")
    return out_path


def _find_manim_output(media_dir: Path) -> Optional[Path]:
    """Locate the produced MP4 in a manim media_dir tree."""
    videos = media_dir / "videos"
    if not videos.exists():
        return None
    candidates = list(videos.rglob("GeneratedScene.mp4"))
    if not candidates:
        candidates = list(videos.rglob("*.mp4"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _run_manim(script_path: Path, media_dir: Path, timeout_s: int) -> Tuple[bool, str]:
    """Run `manim -qh` on the script. Returns (ok, stderr_or_msg)."""
    media_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        CONFIG.manim_path,
        "-qh",
        "--media_dir",
        str(media_dir),
        "--disable_caching",
        str(script_path),
        "GeneratedScene",
    ]
    log.info("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, f"manim timed out after {timeout_s}s"
    except FileNotFoundError as exc:
        return False, f"manim binary not found: {exc}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err[-2000:] if err else "manim returned non-zero exit code"
    return True, ""


def _generate_code(
    client: MiMoClient,
    manim_prompt: str,
    prev_code: Optional[str] = None,
    prev_error: Optional[str] = None,
) -> str:
    if prev_code is not None and prev_error is not None:
        return client.generate_manim_retry(manim_prompt, prev_code, prev_error)
    return client.generate_manim_code(manim_prompt)


def render_manim_scene(
    scene: dict,
    client: MiMoClient,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Path:
    """Render a single manim_animation scene.

    Returns the path to a usable visual file (mp4 on success, png on fallback).
    The path is rooted at `output/scenes/scene_{id}.mp4` or `.png`.
    """
    scene_id = scene["scene_id"]
    out_mp4 = CONFIG.scenes_dir / f"scene_{scene_id:03d}.mp4"
    fallback_png = CONFIG.scenes_dir / f"scene_{scene_id:03d}.png"

    if out_mp4.exists():
        log.info("Scene %d already rendered: %s", scene_id, out_mp4)
        return out_mp4

    prompt = scene.get("manim_prompt") or (
        f"Create a Manim animation illustrating: {scene.get('title','this concept')}."
    )
    title = scene.get("title", "Scene")
    subtitle = scene.get("narration", "")[:200]

    prev_code: Optional[str] = None
    prev_error: Optional[str] = None
    started = time.time()

    for attempt in range(1, max_attempts + 1):
        try:
            code = _generate_code(client, prompt, prev_code, prev_error)
        except Exception as exc:
            log.warning(
                "Attempt %d: LLM call failed for scene %d: %s",
                attempt, scene_id, exc,
            )
            prev_error = str(exc)
            continue

        with tempfile.TemporaryDirectory(prefix=f"visualnote_manim_{scene_id}_") as tmp:
            script_path = Path(tmp) / f"scene_{scene_id:03d}_manim.py"
            try:
                script_path.write_text(code, encoding="utf-8")
            except OSError as exc:
                log.warning("Failed to write script: %s", exc)
                prev_error = str(exc)
                continue
            media_dir = Path(tmp) / "media"
            ok, err = _run_manim(script_path, media_dir, timeout_s)
            if ok:
                produced = _find_manim_output(media_dir)
                if produced and produced.exists():
                    shutil.copyfile(produced, out_mp4)
                    log.info(
                        "Scene %d rendered in %.1fs (attempt %d): %s",
                        scene_id, time.time() - started, attempt, out_mp4,
                    )
                    return out_mp4
                prev_error = "manim exited 0 but no mp4 was produced"
            else:
                prev_error = err
                log.warning(
                    "Attempt %d failed for scene %d: %s",
                    attempt, scene_id, err[:300],
                )

    # All attempts failed → title card fallback.
    log.error(
        "Scene %d: all %d Manim attempts failed; producing title-card fallback",
        scene_id, max_attempts,
    )
    return _make_title_card_png(title, subtitle, fallback_png)


def render_manim_scenes(manifest: dict, client: MiMoClient) -> list[Path]:
    """Render every manim_animation scene in the manifest. Skip non-Manim types."""
    paths: list[Path] = []
    for scene in manifest.get("scenes", []):
        if scene.get("visual_type") != "manim_animation":
            continue
        paths.append(render_manim_scene(scene, client))
    return paths
