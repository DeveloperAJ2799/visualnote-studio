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


def _find_visual(scene: dict) -> Optional[Path]:
    scene_id = scene.get("scene_id")
    if scene_id is None:
        return None
    for suffix in (".mp4", ".png", ".jpg", ".jpeg", ".webp"):
        p = CONFIG.scenes_dir / f"scene_{scene_id:03d}{suffix}"
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

        # Build the panel's inner content as regular (non-clip) elements.
        # The engine only manages the outer panel-wrap visibility; the inner
        # elements (bg-image, title, body) are always present in the DOM but
        # hidden via the parent's data-start/duration. GSAP still animates
        # them by id — the timeline references these exact ids.
        inner_parts: List[str] = []
        if has_image_bg:
            rel = _to_asset_url(visual, project_root)
            inner_parts.append(f'<img class="bg-image" src="{rel}" />')
        if has_video_bg:
            rel = _to_asset_url(visual, project_root)
            inner_parts.append(
                f'<video class="scene-visual" src="{rel}" muted playsinline></video>'
            )
        # The .panel card holds the visible content (accent bar, title, body,
        # footer). bg-image and scene-visual sit behind it via z-index.
        inner_parts.append(
            '<div class="panel">'
            '<div class="panel-accent-bar"></div>'
            f'<h1 class="panel-title" id="title-{sid}">{title_text}</h1>'
            f'<p class="panel-body" id="body-{sid}">{body_text}</p>'
            '<div class="panel-footer">VisualNote \u2022 Module 2</div>'
            '</div>'
        )

        # Single clip per scene: the panel-wrap. All other per-scene content
        # (bg-image, title, body, accent bar) lives INSIDE this div as
        # regular DOM — no class="clip" — so the engine only tracks one
        # visibility boundary per scene on this track.
        layers.append(
            f'<div class="clip panel-wrap" id="panel-{sid}" '
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

    .panel-wrap {{
      position: absolute; inset: 0;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0 40px;
    }}
    .bg-image {{
      position: absolute; inset: 0;
      width: var(--w); height: var(--h);
      object-fit: cover;
      opacity: 0;
      z-index: 0;
      filter: brightness(0.4) saturate(1.2);
    }}
    .scene-visual {{
      position: absolute; inset: 0;
      width: var(--w); height: var(--h);
      object-fit: cover;
      z-index: 1;
    }}

    .panel {{
      position: relative;
      width: min(1400px, 80%);
      max-height: 84%;
      padding: 60px 70px;
      border-radius: 26px;
      background: rgba(10, 14, 39, 0.95);
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.7), 0 0 120px rgba(233, 69, 96, 0.15);
      border: 1px solid rgba(255, 255, 255, 0.1);
      overflow: hidden;
    }}
    .panel-accent-bar {{
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 6px;
      border-radius: 26px 26px 0 0;
      background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent4));
    }}
    .panel-title {{
      margin: 0 0 28px 0;
      font-family: 'Space Grotesk', 'Inter', sans-serif;
      font-size: 64px;
      font-weight: 700;
      line-height: 1.08;
      color: var(--text);
      letter-spacing: -0.02em;
      text-shadow: 0 2px 20px rgba(0, 0, 0, 0.5);
    }}
    .panel-body {{
      margin: 0;
      font-size: 30px;
      line-height: 1.5;
      color: var(--text);
      white-space: pre-wrap;
      text-shadow: 0 1px 10px rgba(0, 0, 0, 0.4);
    }}
    .panel-footer {{
      position: absolute;
      bottom: 24px; right: 32px;
      font-size: 16px;
      letter-spacing: 0.3em;
      text-transform: uppercase;
      color: var(--text-dim);
      font-weight: 600;
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
        has_bg = bool(
            _find_visual(scene) and
            _find_visual(scene).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )

        # Background image Ken Burns (zoom + pan)
        if has_bg:
            gsap_anim_chains.append(
                f"  tl.fromTo('#panel-{sid} .bg-image', "
                f"{{scale:1.1, x:'-3%'}}, "
                f"{{scale:1.0, x:'3%', duration:{dur:.1f}, ease:'none'}}, {start:.3f});"
            )

        # Panel card entrance: slide up + fade
        gsap_anim_chains.append(
            f"  tl.fromTo('#panel-{sid} .panel', "
            f"{{opacity:0, y:60, scale:0.96}}, "
            f"{{opacity:1, y:0, scale:1, duration:0.7, ease:'power3.out'}}, {start:.3f});"
        )

        # Accent bar sweep across top
        gsap_anim_chains.append(
            f"  tl.fromTo('#panel-{sid} .panel-accent-bar', "
            f"{{scaleX:0, transformOrigin:'left'}}, "
            f"{{scaleX:1, duration:0.5, ease:'power2.out'}}, {start + 0.2:.3f});"
        )

        # Title reveal: clip-path wipe from left
        gsap_anim_chains.append(
            f"  tl.fromTo('#title-{sid}', "
            f"{{opacity:0, clipPath:'inset(0 100% 0 0)'}}, "
            f"{{opacity:1, clipPath:'inset(0 0% 0 0)', duration:0.6, ease:'power3.out'}}, {start + 0.3:.3f});"
        )

        # Body text: staggered line-by-line reveal
        gsap_anim_chains.append(
            f"  tl.fromTo('#body-{sid}', "
            f"{{opacity:0, y:20}}, "
            f"{{opacity:1, y:0, duration:0.5, ease:'power2.out'}}, {start + 0.5:.3f});"
        )

        # Exit animations (except last scene)
        if not is_last:
            fade_out_at = start + dur - 0.5
            gsap_anim_chains.append(
                f"  tl.to('#panel-{sid} .panel', "
                f"{{opacity:0, y:-30, scale:0.98, duration:0.4, ease:'power2.in'}}, {fade_out_at:.3f});"
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
        "createdAt": _dt.datetime.utcnow().isoformat() + "Z",
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
    import re as _re
    return bool(_re.search(r"^\s*V[\.\s\S]*h264_nvenc", out.stdout, re.MULTILINE))


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
