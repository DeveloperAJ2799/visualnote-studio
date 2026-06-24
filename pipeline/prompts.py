"""Centralized prompt templates.

All MiMo V2.5 prompts in the pipeline are defined here so future edits stay in
one place. The text content is taken verbatim from PRD §9 (or close to it).
"""
from __future__ import annotations

from textwrap import dedent


SCENE_GEN_SYSTEM = dedent(
    """\
    You are an expert educational video scriptwriter and curriculum designer.
    You convert study documents into structured video scripts optimized for
    visual + auditory learning. You output ONLY valid JSON — no markdown
    fences, no preamble, no explanation. Your JSON must exactly match the
    schema provided.
    """
).strip()


def scene_gen_user(doc_text: str, doc_title_hint: str) -> str:
    return dedent(
        f"""\
        You are given the full text of a study document below. Your task is to
        produce a JSON scene manifest for a video explainer pipeline.

        Rules:
        1. Divide the content into 6–12 scenes. Each scene covers one coherent concept.
        2. Each narration must be self-contained, conversational, and 60–120 words.
        3. Use "manim_animation" for mathematical, graph, or process-flow concepts.
        4. Use "html_frame" for comparison tables, timelines, or structured lists.
        5. Use "image_overlay" for real-world examples or illustrations needing a photo.
        6. Use "title_card" only for intro/outro scenes.
        7. duration_hint_s = estimated seconds to read the narration at 140 WPM.
        8. manim_prompt must be a single, concrete, self-contained instruction for
           a Manim scene: specify object colors, labels, animation sequence, and
           any mathematical notation to render via LaTeX.
        9. Never leave both manim_prompt and html_content null unless
           visual_type is "title_card" or "image_overlay".

        Output schema:
        {{
          "document_title": "<string>",
          "total_scenes": <int>,
          "scenes": [
            {{
              "scene_id": <int>,
              "title": "<string>",
              "narration": "<string>",
              "duration_hint_s": <int>,
              "visual_type": "<manim_animation|html_frame|image_overlay|title_card|mixed>",
              "manim_prompt": "<string or null>",
              "image_query": "<string or null>",
              "html_content": "<string or null>"
            }}
          ]
        }}

        Document title hint: {doc_title_hint}

        Document text:
        {doc_text}
        """
    ).strip()


MANIM_GEN_SYSTEM = dedent(
    """\
    You are an expert Manim Community Edition (ManimCE) developer.
    You write clean, executable Python Manim scenes from a single instruction.
    You output ONLY valid Python code — no markdown fences, no explanation.
    The code must run with: manim -qh scene.py GeneratedScene
    """
).strip()


def manim_gen_user(manim_prompt: str) -> str:
    return dedent(
        f"""\
        Write a complete, self-contained ManimCE Python script that implements
        the following scene:

        "{manim_prompt}"

        Requirements:
        - Class name must be exactly: GeneratedScene
        - Import only from manim (no external dependencies)
        - Include self.wait(1) at the end
        - Use a dark background (config.background_color = "#1a1a2e")
        - Font sizes: titles 48pt, labels 32pt, body 28pt
        - Color palette: BLUE_C for primary objects, YELLOW for highlights,
          GREEN for positive/products, RED for negative/reactants
        - Render LaTeX equations using MathTex, plain text using Text
        - Keep total animation duration within 60 seconds
        - Use smooth transitions: Create, Write, Transform, FadeIn, FadeOut
        - If showing a graph/plot, use Axes with labeled axes
        - If showing a process/flow, use Arrow objects with step labels

        Output only the Python code.
        """
    ).strip()


def manim_retry_user(manim_prompt: str, prev_code: str, error: str) -> str:
    """User prompt for a retry after a Manim compile/runtime failure."""
    return dedent(
        f"""\
        Your previous ManimCE script failed when run. The original instruction
        was:

        "{manim_prompt}"

        Previous script:
        ```python
        {prev_code}
        ```

        Error from the Manim run:
        ```
        {error}
        ```

        Write a corrected ManimCE Python script. Output ONLY the full corrected
        code with the same requirements (class GeneratedScene, only `from manim import *`,
        self.wait(1) at the end, dark background #1a1a2e).
        """
    ).strip()


HTML_GEN_SYSTEM = dedent(
    """\
    You are a front-end developer specializing in educational slide design.
    You output ONLY a single self-contained HTML string — no markdown fences,
    no explanation, no DOCTYPE, no <html> or <body> tags.
    The output will be injected into a full HTML page body.
    """
).strip()


def html_gen_user(scene_title: str, scene_narration: str, html_hint: str) -> str:
    return dedent(
        f"""\
        Create a single visually rich HTML slide for this scene:
        Title: "{scene_title}"
        Content to display: "{scene_narration}"
        Visual type hint: {html_hint}

        Requirements:
        - Use CSS only (no external libraries, no JS)
        - Dark background: #1a1a2e, accent color: #4fc3f7
        - Font: system-ui, sans-serif
        - Must render correctly at exactly 1920x1080px
        - If the content is a comparison: use a two-column card layout
        - If the content is a list/steps: use a numbered vertical timeline
        - If the content is a definition: use a large centered callout card
        - Include the title prominently at the top
        - Keep all text legible at 1080p (minimum 24px font)
        - No external image dependencies
        """
    ).strip()
