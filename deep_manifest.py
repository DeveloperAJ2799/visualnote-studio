"""Custom deep-dive manifest generator for VisualNote.

Overrides the default 6-12 scene limit in pipeline/prompts.py to produce a
10-minute (or longer) explainer with many more scenes. The narration is
structured to walk the viewer through the document in a clear teaching order
with rich detail.

Usage:
    from deep_manifest import generate_deep_manifest
    manifest = generate_deep_manifest(doc_content, client, target_minutes=10)
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional

from pipeline.clients.base import MiMoClient
from pipeline.ingestion import load_doc_content
from pipeline.script_gen import (
    REQUIRED_SCENE_KEYS,
    REQUIRED_TOP_KEYS,
    ALLOWED_VISUAL_TYPES,
    _validate_manifest,
    _repair_manifest,
)
from pipeline.clients.http_client import HTTPClient
from config import CONFIG

log = logging.getLogger(__name__)


DEEP_SYSTEM = dedent(
    """
    You are an expert university-level lecturer and educational video scriptwriter.
    You convert study documents into long-form, deeply explained video scripts
    optimized for visual + auditory learning. You output ONLY valid JSON — no
    markdown fences, no preamble, no explanation.
    """
).strip()


def _build_doc_text(doc_content: Dict[str, Any], max_chars: int = 90_000) -> str:
    chunks: List[str] = []
    title = doc_content.get("document_title") or ""
    if title:
        chunks.append(f"# {title}\n")
    for section in doc_content.get("sections", []):
        heading = section.get("heading")
        if heading:
            chunks.append(f"\n## {heading}\n")
        for block in section.get("blocks", []):
            if block.get("type") == "text":
                chunks.append(block.get("text", ""))
    text = "\n".join(chunks).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[document truncated for prompt size]"
    return text


def _deep_user(doc_text: str, doc_title_hint: str, target_minutes: int) -> str:
    target_scenes = max(15, target_minutes * 2)
    target_words = target_minutes * 140
    return dedent(
        f"""
        You are given the full text of a study document below. Your task is to
        produce a JSON scene manifest for a LONG-FORM deep-dive explainer video
        that runs approximately {target_minutes} minutes (around {target_scenes}
        scenes, ~{target_words} words of narration total).

        STRICT RULES:
        1. Produce EXACTLY {target_scenes} scenes, no more, no fewer.
        2. Each scene covers ONE coherent sub-topic in depth.
        3. Each narration must be 50-120 words, conversational, and richly
           explanatory. The lecturer should TEACH the concept, not just
           summarize it. Use analogies, examples, and step-by-step reasoning.
        4. The first scene MUST be a "title_card" introducing the module.
        5. The last scene MUST be a "title_card" with a recap / conclusion.
        6. Use "manim_animation" for processes, structures, graphs, flows,
           and conceptual diagrams.
        7. Use "html_frame" for comparisons, lists of items, definitions,
           structured taxonomies, and named examples.
        8. Use "image_overlay" when a real-world or biological photograph would
           help the viewer visualize the concept.
        9. duration_hint_s = estimated seconds to read the narration at 140 WPM.
        10. manim_prompt must be ONE concrete self-contained instruction for
            a Manim scene: include object colors, labels, animation sequence,
            and any LaTeX to render. Set null if visual_type is not
            "manim_animation" or "mixed".
        11. html_content must be a short hint ("comparison", "definition",
            "taxonomy", "timeline", etc.). Set null if visual_type is not
            "html_frame".
        12. image_query must be a short noun-phrase describing a real-world
            photo that would illustrate the scene. Set null if visual_type is
            not "image_overlay".

        COVERAGE:
        - Walk through the document in the SAME order as the source material.
        - Cover EVERY major heading and key bullet point at least once.
        - Add a "Why this matters" framing to at least three scenes.
        - End with a "Recap" scene that summarizes the top 5 takeaways.

        Output schema (use exactly this structure):
        {{
          "document_title": "<string>",
          "total_scenes": <int>,
          "scenes": [
            {{
              "scene_id": <int starting at 1>,
              "title": "<short descriptive title>",
              "narration": "<50-120 word deep-dive narration>",
              "duration_hint_s": <int>,
              "visual_type": "<title_card|manim_animation|html_frame|image_overlay|mixed>",
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


def generate_deep_manifest(
    doc_content: Dict[str, Any],
    client: MiMoClient,
    *,
    target_minutes: int = 10,
    max_attempts: int = 2,
    timeout_s: float = 600.0,
    use_council: Optional[bool] = None,
    fast: bool = False,
) -> Dict[str, Any]:
    """Generate a long-form deep-dive manifest for the document.

    By default uses the 5-member council; pass ``use_council=False`` or set
    ``CONFIG.council_enabled=False`` to use the legacy single-LLM path.
    """
    if use_council is None:
        use_council = CONFIG.council_enabled

    if use_council:
        return _generate_deep_manifest_via_council(
            doc_content=doc_content,
            target_minutes=target_minutes,
            fast=fast,
        )

    return _generate_deep_manifest_legacy(
        doc_content=doc_content,
        client=client,
        target_minutes=target_minutes,
        max_attempts=max_attempts,
    )


def _generate_deep_manifest_via_council(
    *,
    doc_content: Dict[str, Any],
    target_minutes: int,
    fast: bool,
) -> Dict[str, Any]:
    """Run the council with a deep-dive target_minutes."""
    from pipeline.council import run_council, save_council_cache
    from pipeline.script_gen import _pdf_hash

    doc_text = _build_doc_text(doc_content)
    title_hint = doc_content.get("document_title", "Untitled Document")
    pdf_hash = _pdf_hash(title_hint, doc_text)
    log.info(
        "Deep manifest via council: target_min=%d fast=%s text_len=%d",
        target_minutes, fast, len(doc_text),
    )
    manifest, state = run_council(
        doc_text=doc_text,
        doc_title_hint=title_hint,
        target_minutes=target_minutes,
        pdf_hash=pdf_hash,
        fast=fast,
    )
    save_council_cache(state)
    if manifest.get("dissent_summary"):
        log.info("Council dissent: %s", manifest["dissent_summary"])
    return manifest


def _generate_deep_manifest_legacy(
    *,
    doc_content: Dict[str, Any],
    client: MiMoClient,
    target_minutes: int,
    max_attempts: int,
) -> Dict[str, Any]:
    """Legacy single-LLM deep-manifest path (no council)."""
    doc_text = _build_doc_text(doc_content)
    title_hint = doc_content.get("document_title", "Untitled Document")
    target_scenes = max(15, target_minutes * 2)

    last_err: Optional[List[str]] = None
    manifest: Optional[Dict[str, Any]] = None
    system_prompt = DEEP_SYSTEM
    user_prompt = _deep_user(doc_text, title_hint, target_minutes)
    log.info(
        "Deep manifest prompt (legacy): %d system chars, %d user chars",
        len(system_prompt),
        len(user_prompt),
    )

    for attempt in range(1, max_attempts + 1):
        log.info(
            "Deep manifest attempt %d (legacy): target %d scenes for %d min",
            attempt, target_scenes, target_minutes,
        )
        if hasattr(client, "_post_chat_kilo"):
            try:
                content = client._post_chat_kilo(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    json_mode=True,
                    temperature=0.4,
                )
            except Exception as exc:
                log.warning("Attempt %d: LLM call failed: %s", attempt, exc)
                last_err = [f"http error: {exc}"]
                continue
        elif hasattr(client, "_call_chat"):
            raw = client._call_chat(
                system=system_prompt,
                user=user_prompt,
                json_mode=True,
            )
            content = raw
        else:
            content = client.generate_scene_manifest(doc_text, title_hint)

        if isinstance(content, dict):
            manifest = content
        elif isinstance(content, str):
            text = content.strip()
            if text.startswith("```"):
                first_nl = text.find("\n")
                if first_nl != -1:
                    text = text[first_nl + 1 :]
                if text.endswith("```"):
                    text = text[:-3]
            text = text.strip()
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                log.warning("Attempt %d: no JSON object in response", attempt)
                last_err = ["no json object"]
                continue
            try:
                manifest = json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                log.warning("Attempt %d: bad JSON: %s", attempt, exc)
                last_err = [f"json parse: {exc}"]
                continue
        else:
            last_err = ["unexpected content type"]
            continue

        manifest = _repair_manifest(manifest)
        last_err = _validate_manifest(manifest)
        if not last_err:
            if len(manifest["scenes"]) < target_scenes - 2:
                log.warning(
                    "Attempt %d: only %d scenes (wanted %d); retrying",
                    attempt, len(manifest["scenes"]), target_scenes,
                )
                last_err = ["too few scenes"]
                continue
            return manifest
        log.warning("Attempt %d: validation issues: %s", attempt, last_err[:3])

    if manifest is None:
        raise RuntimeError("Deep manifest (legacy): no response from LLM")

    manifest = _repair_manifest(manifest)
    errs = _validate_manifest(manifest)
    if errs:
        raise RuntimeError(
            f"Deep manifest (legacy) still invalid after {max_attempts} attempts: {errs[:5]}"
        )
    return manifest
