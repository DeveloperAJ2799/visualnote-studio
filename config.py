"""VisualNote configuration loaded from environment variables."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")


def _bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _detect_ffmpeg() -> str:
    """Locate an ffmpeg binary. Prefer the imageio-ffmpeg bundled copy."""
    override = os.getenv("FFMPEG_PATH")
    if override and Path(override).exists():
        return override
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return bundled
    except Exception:
        pass
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    return "ffmpeg"


def _detect_manim() -> str:
    override = os.getenv("MANIM_PATH")
    if override and Path(override).exists():
        return override
    on_path = shutil.which("manim")
    if on_path:
        return on_path
    return "manim"


@dataclass(frozen=True)
class Config:
    """Runtime configuration for VisualNote.

    All values are loaded from environment variables (or .env).
    """

    project_root: Path = PROJECT_ROOT
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output")
    assets_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output" / "assets")
    extracted_assets_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / "output" / "assets" / "extracted"
    )
    fetched_assets_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / "output" / "assets" / "fetched"
    )
    scenes_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output" / "scenes")
    frames_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output" / "frames")
    final_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "output" / "final")
    templates_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "templates")

    use_mock: bool = field(default_factory=lambda: _bool(os.getenv("MIMO_USE_MOCK"), True))

    mimo_base_url: str = field(
        default_factory=lambda: os.getenv("MIMO_BASE_URL", "https://api.mimo.mi.com/v1")
    )
    mimo_api_key: str = field(default_factory=lambda: os.getenv("MIMO_API_KEY", ""))
    mimo_model: str = field(default_factory=lambda: os.getenv("MIMO_MODEL", "mimo-v2.5"))
    mimo_fallback_model: str = field(
        default_factory=lambda: os.getenv("MIMO_FALLBACK_MODEL", "mimo-v2.5-pro")
    )

    tts_base_url: str = field(
        default_factory=lambda: os.getenv("MIMO_TTS_BASE_URL", "https://api.mimo.mi.com/v1")
    )
    tts_api_key: str = field(default_factory=lambda: os.getenv("MIMO_TTS_API_KEY", ""))
    tts_model: str = field(default_factory=lambda: os.getenv("MIMO_TTS_MODEL", "mimo-v2.5-tts"))
    tts_voice: str = field(default_factory=lambda: os.getenv("MIMO_TTS_VOICE", "instructor"))

    ffmpeg_path: str = field(default_factory=_detect_ffmpeg)
    manim_path: str = field(default_factory=_detect_manim)

    default_resolution: str = field(
        default_factory=lambda: os.getenv("DEFAULT_RESOLUTION", "1080p")
    )

    coqui_tts_model: str = field(default_factory=lambda: os.getenv("COQUI_TTS_MODEL", ""))
    coqui_tts_voice: str = field(default_factory=lambda: os.getenv("COQUI_TTS_VOICE", ""))

    def ensure_dirs(self) -> None:
        """Create all output directories if they do not exist."""
        for path in (
            self.output_dir,
            self.assets_dir,
            self.extracted_assets_dir,
            self.fetched_assets_dir,
            self.scenes_dir,
            self.frames_dir,
            self.final_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
CONFIG.ensure_dirs()
