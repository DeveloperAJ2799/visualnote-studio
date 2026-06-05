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


# Council config helpers: read defaults from pipeline/council/council_config.json
# so model names live in a config file, not in code. Env vars (COUNCIL_*)
# still override these at runtime.
def _council_default(key: str, fallback):
    try:
        from pipeline.council.config import load_council_config
        return load_council_config().get(key, fallback)
    except Exception:
        return fallback


def _council_member_default(member: str, key: str, fallback):
    try:
        from pipeline.council.config import get_member_config
        return get_member_config(member).get(key, fallback)
    except Exception:
        return fallback


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

    use_mock: bool = field(default_factory=lambda: _bool(os.getenv("MIMO_USE_MOCK"), False))

    # --- LLM (Kilo Code AI Gateway) ---
    kilo_base_url: str = field(
        default_factory=lambda: os.getenv("KILO_BASE_URL", "https://api.kilo.ai/api/gateway")
    )
    kilo_api_key: str = field(default_factory=lambda: os.getenv("KILO_API_KEY", ""))
    kilo_model: str = field(
        default_factory=lambda: os.getenv("KILO_MODEL", "anthropic/claude-sonnet-4.5")
    )
    kilo_fallback_model: str = field(
        default_factory=lambda: os.getenv("KILO_FALLBACK_MODEL", "anthropic/claude-sonnet-4")
    )

    # --- TTS (Xiaomi MiMo Open Platform) ---
    tts_base_url: str = field(
        default_factory=lambda: os.getenv("MIMO_TTS_BASE_URL", "https://api.xiaomimimo.com/v1")
    )
    tts_api_key: str = field(default_factory=lambda: os.getenv("MIMO_TTS_API_KEY", ""))
    tts_model: str = field(default_factory=lambda: os.getenv("MIMO_TTS_MODEL", "mimo-v2.5-tts"))
    tts_voice: str = field(
        default_factory=lambda: os.getenv("MIMO_TTS_VOICE", "Chloe")
    )

    ffmpeg_path: str = field(default_factory=_detect_ffmpeg)
    manim_path: str = field(default_factory=_detect_manim)

    default_resolution: str = field(
        default_factory=lambda: os.getenv("DEFAULT_RESOLUTION", "1080p")
    )

    coqui_tts_model: str = field(default_factory=lambda: os.getenv("COQUI_TTS_MODEL", ""))
    coqui_tts_voice: str = field(default_factory=lambda: os.getenv("COQUI_TTS_VOICE", ""))

    # --- Image Generation (NVIDIA NIM Qwen-Image) ---
    nvidia_nim_api_key: str = field(
        default_factory=lambda: os.getenv("NVIDIA_NIM_API_KEY", "")
    )

    # --- Council (5-member deliberation; free models only) ---
    # Defaults come from pipeline/council/council_config.json.
    # Env vars (COUNCIL_*_MODEL, COUNCIL_ENABLED, etc.) override at runtime.
    council_enabled: bool = field(
        default_factory=lambda: _bool(
            os.getenv("COUNCIL_ENABLED"),
            _council_default("enabled", True),
        )
    )
    council_max_retries: int = field(
        default_factory=lambda: int(
            os.getenv("COUNCIL_MAX_RETRIES")
            or str(_council_default("max_retries", 3))
        )
    )
    council_confidence_threshold: float = field(
        default_factory=lambda: float(
            os.getenv("COUNCIL_CONFIDENCE_THRESHOLD")
            or str(_council_default("confidence_threshold", 0.6))
        )
    )
    council_scriptwriter_model: str = field(
        default_factory=lambda: os.getenv(
            "COUNCIL_SCRIPTWRITER_MODEL",
            _council_member_default("scriptwriter", "model", ""),
        )
    )
    council_visual_designer_model: str = field(
        default_factory=lambda: os.getenv(
            "COUNCIL_VISUAL_DESIGNER_MODEL",
            _council_member_default("visual_designer", "model", ""),
        )
    )
    council_fact_checker_model: str = field(
        default_factory=lambda: os.getenv(
            "COUNCIL_FACT_CHECKER_MODEL",
            _council_member_default("fact_checker", "model", ""),
        )
    )
    council_pedagogy_reviewer_model: str = field(
        default_factory=lambda: os.getenv(
            "COUNCIL_PEDAGOGY_REVIEWER_MODEL",
            _council_member_default("pedagogy_reviewer", "model", ""),
        )
    )
    council_chairman_model: str = field(
        default_factory=lambda: os.getenv(
            "COUNCIL_CHAIRMAN_MODEL",
            _council_member_default("chairman", "model", ""),
        )
    )

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
