"""Structural Protocols for the MiMo V2.5 LLM and TTS clients.

All pipeline modules consume these Protocols. Two concrete implementations are
provided: `HTTPClient` (real API) and `MockClient` (deterministic, no network).
"""
from __future__ import annotations

from typing import Any, Dict, Protocol


class MiMoClient(Protocol):
    """MiMo V2.5 chat-completions client surface used by the pipeline."""

    def generate_scene_manifest(
        self, doc_text: str, doc_title_hint: str
    ) -> Dict[str, Any]:
        """Produce the scene manifest JSON for a full document."""
        ...

    def generate_manim_code(self, manim_prompt: str) -> str:
        """Produce a self-contained ManimCE Python script for one scene."""
        ...

    def generate_manim_retry(
        self, manim_prompt: str, prev_code: str, error: str
    ) -> str:
        """Produce a corrected ManimCE script after a compile/runtime failure."""
        ...

    def generate_html_frame(
        self, scene_title: str, scene_narration: str, html_hint: str
    ) -> str:
        """Produce an HTML body fragment for a static educational slide."""
        ...


class TTSClient(Protocol):
    """TTS client surface used by the pipeline."""

    def synthesize(self, text: str, voice: str = "instructor") -> bytes:
        """Synthesize speech and return WAV bytes."""
        ...
