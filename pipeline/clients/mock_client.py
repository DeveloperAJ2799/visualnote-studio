"""Deterministic mock implementations of MiMoClient and TTSClient.

These let the entire pipeline run end-to-end without any API calls. The mock
manifest is schema-valid and matches the structure in PRD §8. The mock Manim
script renders a real (if simple) animation. The mock TTS returns a silent
WAV of the requested text's notional length.
"""
from __future__ import annotations

import io
import math
import struct
import textwrap
import wave
from typing import Any, Dict


def _silent_wav(duration_s: float, sample_rate: int = 22050) -> bytes:
    """Return WAV bytes of silence of the given duration."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)
    return buf.getvalue()


SAMPLE_MANIM_SCRIPT = textwrap.dedent(
    '''\
    from manim import *

    class GeneratedScene(Scene):
        def construct(self):
            config.background_color = "#1a1a2e"
            title = Text("Mock Generated Scene", font_size=48, color=BLUE_C)
            sub = Text("VisualNote mock client", font_size=28, color=YELLOW)
            sub.next_to(title, DOWN, buff=0.5)
            self.play(Write(title), run_time=1.2)
            self.play(FadeIn(sub, shift=UP), run_time=1.0)
            self.wait(2.0)
            self.play(FadeOut(title), FadeOut(sub))
    '''
)


SAMPLE_HTML_FRAME = textwrap.dedent(
    '''\
    <div style="
        width: 1920px;
        height: 1080px;
        background: #1a1a2e;
        color: #f0f0f0;
        font-family: system-ui, -apple-system, sans-serif;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        padding: 80px;
        box-sizing: border-box;
    ">
        <h1 style="font-size: 72px; color: #4fc3f7; margin: 0 0 40px 0;">
            {title}
        </h1>
        <p style="font-size: 32px; line-height: 1.5; max-width: 1400px; text-align: center;">
            {body}
        </p>
    </div>
    '''
)


def _build_manifest(doc_text: str, doc_title_hint: str) -> Dict[str, Any]:
    """Return a deterministic, schema-valid 4-scene manifest."""
    title = doc_title_hint.strip() or "Untitled Document"
    raw = doc_text.strip()
    excerpt = raw[:240] if raw else "This is a mock narration generated for development."

    return {
        "document_title": title,
        "total_scenes": 4,
        "scenes": [
            {
                "scene_id": 1,
                "title": "Introduction",
                "narration": (
                    f"Welcome. In this explainer we will walk through the key ideas "
                    f"from {title}. The document begins by laying the foundations "
                    f"and motivating the rest of the material. {excerpt}"
                ),
                "duration_hint_s": 60,
                "visual_type": "title_card",
                "manim_prompt": None,
                "image_query": None,
                "html_content": None,
            },
            {
                "scene_id": 2,
                "title": "Core Concept",
                "narration": (
                    "Now we move to the core concept. The author defines the central "
                    "terms, sets up notation, and walks through a worked example. "
                    "Pay attention to the relationship between the variables, which "
                    "we will reuse in the next scene."
                ),
                "duration_hint_s": 75,
                "visual_type": "manim_animation",
                "manim_prompt": (
                    "Animate two labeled boxes connected by an arrow. The left box "
                    "is labeled 'Input' in BLUE_C, the right box is labeled 'Output' "
                    "in GREEN. A short caption below reads 'Transformation' in "
                    "YELLOW. Fade the arrow tip with a small pulse."
                ),
                "image_query": None,
                "html_content": None,
            },
            {
                "scene_id": 3,
                "title": "Comparison",
                "narration": (
                    "Here is a side-by-side comparison. Notice the trade-offs between "
                    "the two approaches. We will revisit these in the final summary."
                ),
                "duration_hint_s": 50,
                "visual_type": "html_frame",
                "manim_prompt": None,
                "image_query": None,
                "html_content": "comparison",
            },
            {
                "scene_id": 4,
                "title": "Summary",
                "narration": (
                    "To summarize, the document covers the foundations, the core "
                    "concept, and the trade-offs. Use this explainer as a starting "
                    "point before re-reading the original notes."
                ),
                "duration_hint_s": 40,
                "visual_type": "title_card",
                "manim_prompt": None,
                "image_query": None,
                "html_content": None,
            },
        ],
    }


class MockClient:
    """Implements both MiMoClient and TTSClient Protocols with deterministic data."""

    def generate_scene_manifest(
        self, doc_text: str, doc_title_hint: str
    ) -> Dict[str, Any]:
        return _build_manifest(doc_text, doc_title_hint)

    def generate_manim_code(self, manim_prompt: str) -> str:
        return SAMPLE_MANIM_SCRIPT

    def generate_manim_retry(
        self, manim_prompt: str, prev_code: str, error: str
    ) -> str:
        # The mock always returns the same valid script; retry is a no-op.
        return SAMPLE_MANIM_SCRIPT

    def generate_html_frame(
        self, scene_title: str, scene_narration: str, html_hint: str
    ) -> str:
        body = scene_narration.strip()
        if len(body) > 320:
            body = body[:317] + "..."
        return SAMPLE_HTML_FRAME.format(
            title=scene_title.strip() or "Scene",
            body=body or "Mock slide content.",
        )

    def synthesize(self, text: str, voice: str = "Chloe") -> bytes:
        words = max(1, len(text.split()))
        duration = max(1.5, min(20.0, words / 2.4))
        return _silent_wav(duration)
