"""TTS narration synthesis.

For each scene in the manifest:
  1. Call the TTSClient to synthesize the narration text to WAV bytes.
  2. Save as `output/scenes/scene_{id:03d}_audio.wav`.
  3. Probe the WAV duration with ffprobe and return (wav_path, duration_s).

If the primary TTS client fails and `MIMO_TTS_API_KEY` is unset or the call
errors, the function falls back to:
  - Coqui TTS (local) if `COQUI_TTS_MODEL` is configured and importable.
  - A silent WAV of a duration estimated from the word count.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from config import CONFIG
from pipeline.clients.base import TTSClient

log = logging.getLogger(__name__)

_WORDS_PER_SECOND = 2.3  # ~140 WPM
_PAUSE_TAG_RE = re.compile(r"\[pause\]", re.IGNORECASE)


def _probe_wav_duration(wav_path: Path) -> float:
    """Return the duration in seconds, using ffmpeg if available else stdlib wave."""
    try:
        out = subprocess.run(
            [
                CONFIG.ffmpeg_path,
                "-i", str(wav_path),
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # ffmpeg prints duration info to stderr; parse "Duration: HH:MM:SS.xx"
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out.stderr)
        if match:
            h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
            return h * 3600 + m * 60 + s
    except Exception as exc:
        log.debug("ffmpeg duration probe failed: %s", exc)
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            return frames / rate
    except Exception as exc:
        log.warning("wave duration probe failed: %s", exc)
        return 0.0


def _silent_wav_for_text(text: str) -> bytes:
    """Build a silent WAV whose length is estimated from the text word count."""
    words = max(1, len(text.split()))
    pause_extra = 0.5 * len(_PAUSE_TAG_RE.findall(text))
    duration = max(1.5, min(30.0, words / _WORDS_PER_SECOND + pause_extra))
    n_samples = int(duration * 22050)
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


def _coqui_synthesize(text: str, model_name: str, voice: str) -> Optional[bytes]:
    """Try to synthesize via local Coqui TTS. Returns WAV bytes or None on failure."""
    try:
        from TTS.api import TTS  # type: ignore
    except Exception as exc:
        log.debug("Coqui TTS not importable: %s", exc)
        return None
    try:
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        tts = TTS(model_name=model_name, progress_bar=False, gpu=False)
        kwargs = {"text": text, "file_path": tmp_path}
        if voice:
            kwargs["speaker"] = voice
        tts.tts_to_file(**kwargs)
        with open(tmp_path, "rb") as fh:
            data = fh.read()
        os.unlink(tmp_path)
        return data
    except Exception as exc:
        log.warning("Coqui TTS failed: %s", exc)
        return None


def _synthesize_with_fallback(
    text: str,
    voice: str,
    primary: TTSClient,
) -> bytes:
    """Try the primary client, then Coqui, then silent WAV."""
    try:
        return primary.synthesize(text, voice=voice)
    except Exception as exc:
        log.warning("Primary TTS failed (%s); trying Coqui fallback", exc)
    if CONFIG.coqui_tts_model:
        coqui = _coqui_synthesize(text, CONFIG.coqui_tts_model, CONFIG.coqui_tts_voice)
        if coqui:
            return coqui
    log.warning("All TTS paths failed; emitting silent WAV")
    return _silent_wav_for_text(text)


def synthesize_scene(
    scene: dict,
    tts_client: TTSClient,
    voice: Optional[str] = None,
) -> Tuple[Path, float]:
    """Synthesize narration for one scene. Returns (wav_path, duration_s)."""
    scene_id = scene["scene_id"]
    wav_path = CONFIG.scenes_dir / f"scene_{scene_id:03d}_audio.wav"
    voice = voice or CONFIG.tts_voice
    text = (scene.get("narration") or "").strip()
    if not text:
        log.warning("Scene %d has empty narration; producing 1.5s silence", scene_id)
        text = "."

    if wav_path.exists():
        duration = _probe_wav_duration(wav_path)
        log.info("Scene %d audio already exists: %s (%.2fs)", scene_id, wav_path, duration)
        return wav_path, duration

    wav_bytes = _synthesize_with_fallback(text, voice, tts_client)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path.write_bytes(wav_bytes)
    duration = _probe_wav_duration(wav_path)
    log.info(
        "Scene %d audio: %s (%.2fs, %d bytes, voice=%s)",
        scene_id, wav_path, duration, len(wav_bytes), voice,
    )
    return wav_path, duration
