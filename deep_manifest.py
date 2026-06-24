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


# ---------------------------------------------------------------------------
# Frame style assignment (maps visual_type / html_content → layout)
# ---------------------------------------------------------------------------

_FRAME_STYLES = [
    "title_hero", "image_left", "image_right", "diagram_center",
    "split_compare", "listing_columns", "full_bleed", "steps_horizontal",
    "stats_grid", "chapter_marker", "quote_callout", "text_only",
    "type_columns", "flow_chain", "process_flow", "infographic",
    "venn_diagram", "pyramid", "cycle_diagram", "funnel",
    "flowchart", "pie_chart", "bar_chart", "annotated_diagram",
]


def _assign_frame_styles(manifest: dict) -> dict:
    """Ensure every scene has a ``frame_style`` field.

    If the LLM already provided one, keep it.  Otherwise derive it from
    ``visual_type`` + ``html_content`` with heuristics that detect content
    patterns like type listings, multi-step processes, flow chains,
    overlapping concepts, hierarchies, cycles, and data visualizations.
    """
    scenes = manifest.get("scenes", [])
    total = len(scenes)
    for i, scene in enumerate(scenes):
        if scene.get("frame_style"):
            continue
        vt = scene.get("visual_type", "title_card")
        html = (scene.get("html_content") or "").lower()
        title = (scene.get("title") or "").lower()
        narration = (scene.get("narration") or "").lower()

        if i == 0 or i == total - 1:
            scene["frame_style"] = "title_hero"
        elif vt == "title_card":
            scene["frame_style"] = "chapter_marker"
        elif vt == "html_frame":
            # Priority order: most specific patterns first
            if any(k in html for k in ("venn", "overlap", "shared", "common between")):
                scene["frame_style"] = "venn_diagram"
            elif any(k in html for k in ("pyramid", "hierarchy", "levels of", "tiers")):
                scene["frame_style"] = "pyramid"
            elif any(k in html for k in ("cycle", "circular", "loop", "recurring", "repeats")):
                scene["frame_style"] = "cycle_diagram"
            elif any(k in html for k in ("funnel", "filter", "narrowing", "reduction")):
                scene["frame_style"] = "funnel"
            elif any(k in html for k in ("flowchart", "decision", "if-then", "branch")):
                scene["frame_style"] = "flowchart"
            elif any(k in html for k in ("pie", "percentage", "proportion", "share of", "breakdown")):
                scene["frame_style"] = "pie_chart"
            elif any(k in html for k in ("bar chart", "compare quantities", "energy yield", "amount")):
                scene["frame_style"] = "bar_chart"
            elif any(k in html for k in ("annotate", "labeled diagram", "parts of", "anatomy")):
                scene["frame_style"] = "annotated_diagram"
            elif any(k in html for k in ("types", "categories", "taxonomy", "classification", "kinds")):
                scene["frame_style"] = "type_columns"
            elif any(k in html for k in ("comparison", "vs", "versus", "difference")):
                scene["frame_style"] = "split_compare"
            elif any(k in html for k in ("list", "items", "uses", "functions", "roles")):
                scene["frame_style"] = "listing_columns"
            elif any(k in html for k in ("definition", "define", "what is")):
                scene["frame_style"] = "text_only"
            elif any(k in html for k in ("timeline", "steps", "process", "sequence")):
                scene["frame_style"] = "steps_horizontal"
            elif any(k in html for k in ("statistics", "numbers", "data", "percent")):
                scene["frame_style"] = "stats_grid"
            elif any(k in html for k in ("flow", "chain", "pathway")):
                scene["frame_style"] = "flow_chain"
            else:
                scene["frame_style"] = "listing_columns"
        elif vt == "manim_animation":
            # Detect multi-step processes
            process_keywords = ("step 1", "first", "then", "next", "finally",
                                "process", "chain", "cycle", "pathway", "flow")
            if any(k in narration for k in process_keywords):
                # Check if it's a chain/flow (connected steps)
                chain_keywords = ("chain", "cycle", "pathway", "flow",
                                  "photosynthesis", "respiration", "digestion")
                if any(k in narration for k in chain_keywords):
                    scene["frame_style"] = "flow_chain"
                else:
                    scene["frame_style"] = "process_flow"
            else:
                scene["frame_style"] = "diagram_center"
        elif vt == "image_overlay":
            # Check for annotated diagram potential
            if any(k in narration for k in ("anatomy", "parts of", "labeled", "structure of")):
                scene["frame_style"] = "annotated_diagram"
            elif i % 2 == 0:
                scene["frame_style"] = "image_left"
            else:
                scene["frame_style"] = "image_right"
        else:
            scene["frame_style"] = "text_only"
    return manifest


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
        8. Use "image_overlay" when a real-world photograph or illustration
           would help the viewer visualize the concept.
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
              "frame_style": "<see FRAME STYLES below>",
              "manim_prompt": "<string or null>",
              "image_query": "<string or null>",
              "html_content": "<string or null>"
            }}
          ]
        }}

        FRAME STYLES (pick the best match for each scene):
        - "title_hero": Opening/closing title cards, section introductions.
          Large centered title text, minimal body. Use for scene 1 and last scene.
        - "text_only": Conceptual explanations, definitions, "why this matters"
          scenes. Centered text only, no image. Good for narration-heavy scenes.
        - "quote_callout": Key quotes, memorable one-liners, analogies.
          Centered large quote-style text.
        - "chapter_marker": Section dividers between major topics.
          Large topic number + title centered.
        - "image_left": Scenes with a strong diagram/image on the left, text
          on the right. Use when image_query or manim_prompt is present.
        - "image_right": Same as image_left but image on the right side.
          Alternate with image_left for visual variety.
        - "diagram_center": Complex diagrams or processes shown center-stage.
          Use when manim_prompt describes a multi-step process.
        - "split_compare": Side-by-side comparisons (X vs Y).
          Use when html_content mentions "comparison", "vs", or "difference".
        - "listing_columns": Lists of items, uses, functions, roles.
          3-column card grid. Use when html_content mentions "list", "uses",
          "functions", "roles", or narration has 3+ bullet-style items.
        - "type_columns": Multi-column layout for showing TYPES/CATEGORIES
          side by side. Each type gets its own column with title + description.
          Use when html_content mentions "types", "categories", "taxonomy",
          "classification", or when listing distinct kinds of something
          (e.g., primary/secondary/tertiary proteins, monosaccharide/disaccharide).
        - "flow_chain": Connected nodes showing a multi-step PROCESS or CYCLE
          with arrows between them. Elements animate in sequence (e.g., sun
          appears first, then water, then glucose). Use for photosynthesis,
          respiration, digestion, metabolic pathways, or any chain reaction.
        - "process_flow": Linear input → process → output diagram. Shows
          inputs on the left, transformation in the middle, outputs on the
          right. Use for chemical reactions, cause-effect chains, or simple
          3-step transformations.
        - "infographic": Complex multi-element diagram combining stats, icons,
          and connected elements. Use for scenes that need rich visual
          explanation with multiple data points or concepts.
        - "full_bleed": Dramatic full-screen image with text overlay.
          Use for visually striking scenes (e.g., cell close-up, DNA helix).
        - "steps_horizontal": Numbered step-by-step processes.
          Horizontal numbered timeline. Use when narration describes a
          sequence (1. 2. 3. etc).
        - "stats_grid": Key statistics or numerical highlights.
          2x2 grid of stat cards. Use when narration has numbers/percentages.
        - "venn_diagram": Overlapping concepts showing shared and unique traits.
          2-3 overlapping circles with labels. Use when html_content mentions
          "overlap", "shared", "common", "venn", or comparing 2-3 things
          with both similarities and differences.
        - "pyramid": Hierarchical levels from bottom (largest) to top (smallest).
          Use when html_content mentions "pyramid", "hierarchy", "levels",
          "tiers", or content has a clear bottom-up importance structure
          (e.g., Maslow's hierarchy, biological organization levels).
        - "cycle_diagram": Circular recurring process with arrows forming a loop.
          Use when html_content mentions "cycle", "circular", "loop",
          "recurring", "repeats", or content describes a process that
          returns to its starting point (e.g., cell cycle, life cycles).
        - "funnel": Inverted pyramid showing progressive reduction/filtering.
          Use when html_content mentions "funnel", "filter", "narrowing",
          "reduction", or content shows stages where quantity decreases
          (e.g., substrate selection, information processing).
        - "flowchart": Connected shapes (diamonds for decisions, rectangles
          for processes) with labeled arrows. Use when html_content mentions
          "flowchart", "decision", "if-then", "branch", or content has
          conditional logic or branching paths.
        - "pie_chart": Circular chart divided into proportional slices.
          Use when html_content mentions "pie", "percentage", "proportion",
          "share", "breakdown", or narration has 3-6 percentage values
          that add up to 100%.
        - "bar_chart": Vertical or horizontal bars comparing quantities.
          Use when html_content mentions "bar chart", "compare quantities",
          "energy yield", "amount", or narration has 3+ numerical values
          to compare across categories.
        - "annotated_diagram": Central image/diagram with labeled callout
          lines pointing to parts. Use when html_content mentions "annotate",
          "labeled diagram", "parts of", "anatomy", or when explaining
          the components of a structure (e.g., cell parts, molecule structure).

        RULES for frame_style:
        - First and last scene MUST be "title_hero".
        - Scenes with visual_type "title_card" → "title_hero" or "chapter_marker".
        - Scenes with visual_type "html_frame" → map based on html_content:
            "overlap"/"shared"/"common" → "venn_diagram"
            "pyramid"/"hierarchy"/"levels" → "pyramid"
            "cycle"/"circular"/"loop" → "cycle_diagram"
            "funnel"/"filter"/"narrowing" → "funnel"
            "flowchart"/"decision"/"branch" → "flowchart"
            "pie"/"percentage"/"proportion" → "pie_chart"
            "bar chart"/"quantities"/"amount" → "bar_chart"
            "annotate"/"labeled"/"parts of" → "annotated_diagram"
            "comparison"/"vs" → "split_compare"
            "types"/"categories"/"taxonomy" → "type_columns"
            "list"/"uses"/"functions" → "listing_columns"
            "definition" → "text_only"
            "timeline"/"steps" → "steps_horizontal"
            "statistics"/"numbers" → "stats_grid"
            "flow"/"chain" → "flow_chain"
            default → "listing_columns"
        - Scenes with visual_type "manim_animation" → map based on narration:
            Multi-step processes with "chain"/"cycle"/"pathway" → "flow_chain"
            Simple 3-step processes → "process_flow"
            Other diagrams → "diagram_center"
        - Scenes with visual_type "image_overlay" → check for "anatomy"/"parts"
          → "annotated_diagram", else "image_left" or "image_right".
        - Alternate between left/right positions for visual variety.

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
    council_config: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generate a long-form deep-dive manifest for the document.

    By default uses the legacy single-LLM path (1 call, fast). Pass
    ``use_council=True`` or set ``CONFIG.council_enabled=True`` to use the
    5-member council (3-5 calls, slower but more thorough).

    Args:
        council_config: Optional path to a custom ``council_config.json``
            to use for this run. Lets you swap members, models, system
            prompts, and phase structure without touching Python.
    """
    if use_council is None:
        use_council = CONFIG.council_enabled

    if use_council:
        return _generate_deep_manifest_via_council(
            doc_content=doc_content,
            target_minutes=target_minutes,
            fast=fast,
            council_config_path=council_config,
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
    council_config_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run the council with a deep-dive target_minutes."""
    from pipeline.council import run_council, save_council_cache, load_council_cache
    from pipeline.script_gen import _pdf_hash

    doc_text = _build_doc_text(doc_content)
    title_hint = doc_content.get("document_title", "Untitled Document")
    pdf_hash = _pdf_hash(title_hint, doc_text)

    # Check council cache first — skip all 5 LLM calls if hit
    cached = load_council_cache(pdf_hash)
    if cached:
        log.info("Council cache hit for %s — skipping LLM calls", pdf_hash[:8])
        return cached

    log.info(
        "Deep manifest via council: target_min=%d fast=%s text_len=%d config=%s",
        target_minutes, fast, len(doc_text),
        council_config_path or "<default>",
    )
    manifest, state = run_council(
        doc_text=doc_text,
        doc_title_hint=title_hint,
        target_minutes=target_minutes,
        pdf_hash=pdf_hash,
        fast=fast,
        council_config_path=council_config_path,
    )
    manifest = _assign_frame_styles(manifest)
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
        manifest = _assign_frame_styles(manifest)
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
    manifest = _assign_frame_styles(manifest)
    errs = _validate_manifest(manifest)
    if errs:
        raise RuntimeError(
            f"Deep manifest (legacy) still invalid after {max_attempts} attempts: {errs[:5]}"
        )
    return manifest
