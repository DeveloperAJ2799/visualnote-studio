"""Scene Planner

Takes narration text and generates structured visual_concept JSON
that describes what should appear on screen. This is the mandatory
"scene plan" step in the IGWANI pipeline:

    narration → scene plan (visual_concept) → LLM code → render

The planner uses LLM to break narration into visual steps and
assign appropriate IGWANI layouts/components to each.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from config import CONFIG
from pipeline.clients.http_client import HTTPClient
from pipeline.motion_prompt import get_system_prompt

log = logging.getLogger(__name__)

SCENE_PLAN_SYSTEM = """You are an IGWANI scene planner. Your job is to break narration text into
visual scenes for an educational video. Each scene is ONE visual idea — not a list of points.

# Rules
1. One narration sentence = one scene = ~4-6 seconds
2. Each scene MUST have a visual_concept — what to SHOW, not what to SAY
3. NO bullet lists. Visual concepts only.
4. Choose the best IGWANI layout for each concept:
   - "big_reveal" — one dramatic text/number filling the screen (key terms, stats)
   - "split_compare" — two-column visual comparison (before/after, pros/cons)
   - "callout_focus" — single element with heavy annotation (highlighting one thing)
   - "flow_diagram" — multi-step process with connected nodes (how something works)
   - "definition_card" — key term with visual illustration (vocabulary, concepts)
   - "equation_build" — formula that builds piece by piece (math, chemistry, code)
   - "title_card" — opening titles, section headers
   - "stat_beat" — big number + annotation circle

5. **VARIETY IS MANDATORY.** No more than 2 consecutive scenes can use the same layout.
   Alternate between different patterns to keep viewers engaged.
6. Assign timing: entry_frame and duration for each element
7. Use amber accent by default. Coral only for warnings/contrasts.
8. Keep it tight: 3-5 elements per scene max.

# Output Format
Return a JSON array of scene objects. Each scene:
{
  "scene_id": 1,
  "title": "Short title",
  "layout": "big_reveal",
  "narration": "Original narration text",
  "duration_s": 5,
  "visual_concept": "Description of what to show on screen",
  "elements": [
    {
      "type": "node" | "connector" | "text" | "code" | "annotation" | "stat" | "callout",
      "label": "Text to display",
      "position": "center" | "left" | "right" | "top" | "bottom",
      "enter_frame": 10,
      "annotation": {
        "type": "circle" | "underline" | "bracket" | "arrow",
        "frame": 30
      }
    }
  ]
}
"""


def _build_client() -> HTTPClient:
    return HTTPClient(
        kilo_base_url=CONFIG.kilo_base_url,
        kilo_api_key=CONFIG.kilo_api_key,
        kilo_model=CONFIG.kilo_model,
        tts_base_url=CONFIG.tts_base_url,
        tts_api_key=CONFIG.tts_api_key,
        tts_model=CONFIG.tts_model,
        timeout_s=120.0,
    )


def _parse_json_response(response: str) -> Any:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in code block
    patterns = [
        r"```json\s*\n(.*?)```",
        r"```\s*\n(.*?)```",
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())

    # Try parsing the whole response as JSON
    return json.loads(response.strip())


def _validate_scene_plan(scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate the scene plan structure."""
    errors = []
    warnings = []

    if not scenes:
        errors.append("No scenes generated")
        return {"valid": False, "errors": errors, "warnings": warnings}

    for i, scene in enumerate(scenes):
        scene_num = i + 1

        if "layout" not in scene:
            warnings.append(f"Scene {scene_num}: missing layout")
        elif scene["layout"] not in [
            "big_reveal", "split_compare", "callout_focus", "flow_diagram",
            "definition_card", "equation_build", "title_card", "stat_beat",
            # Legacy layouts (still accepted)
            "diagram", "process_flow", "comparison", "code_reveal",
            "annotation_focus", "quote_highlight",
        ]:
            warnings.append(f"Scene {scene_num}: unknown layout '{scene['layout']}'")

        if "visual_concept" not in scene:
            errors.append(f"Scene {scene_num}: missing visual_concept (mandatory)")

        if "elements" not in scene or not scene.get("elements"):
            warnings.append(f"Scene {scene_num}: no elements defined")

        # Check for anti-patterns
        concept = scene.get("visual_concept", "").lower()
        if "bullet" in concept or "list" in concept or "•" in concept:
            errors.append(f"Scene {scene_num}: visual_concept mentions bullets/lists")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def plan_scenes(
    narration: str,
    course_context: str = "",
    target_duration_s: float = 180.0,
) -> Dict[str, Any]:
    """Plan scenes from narration text.

    Args:
        narration: Full narration text for the video
        course_context: Course title, module info, etc.
        target_duration_s: Target total duration in seconds

    Returns:
        Dict with keys: scenes, validation, metadata
    """
    client = _build_client()

    # Split narration into paragraphs or sentences for planning
    paragraphs = [p.strip() for p in narration.split("\n") if p.strip()]
    if not paragraphs:
        paragraphs = [narration]

    user_prompt = f"""Plan visual scenes for this narration.

Course Context: {course_context or "Educational video"}
Target Duration: {target_duration_s:.0f} seconds
Target FPS: 30

Narration:
{json.dumps(paragraphs, indent=2)}

Generate a JSON array of scenes following the IGWANI scene plan format.
One narration sentence = one scene = roughly 4-6 seconds.
Each scene MUST have a visual_concept describing what to SHOW on screen.

Return ONLY the JSON array, no other text:"""

    try:
        raw = client._post_chat_kilo(
            messages=[
                {"role": "system", "content": SCENE_PLAN_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=False,
            temperature=0.5,
        )

        if not raw:
            return {
                "scenes": [],
                "validation": {"valid": False, "errors": ["Empty LLM response"], "warnings": []},
                "metadata": {"narration_length": len(narration), "paragraph_count": len(paragraphs)},
            }

        scenes = _parse_json_response(raw)

        # Ensure it's a list
        if isinstance(scenes, dict) and "scenes" in scenes:
            scenes = scenes["scenes"]
        elif not isinstance(scenes, list):
            scenes = [scenes]

        # Validate
        validation = _validate_scene_plan(scenes)

        # Assign sequential IDs
        for i, scene in enumerate(scenes):
            scene.setdefault("scene_id", i + 1)

        return {
            "scenes": scenes,
            "validation": validation,
            "metadata": {
                "narration_length": len(narration),
                "paragraph_count": len(paragraphs),
                "scene_count": len(scenes),
                "total_planned_duration_s": sum(s.get("duration_s", 5) for s in scenes),
            },
        }

    except json.JSONDecodeError as e:
        log.error("Failed to parse scene plan JSON: %s", e)
        return {
            "scenes": [],
            "validation": {"valid": False, "errors": [f"JSON parse error: {e}"], "warnings": []},
            "metadata": {},
        }
    except Exception as e:
        log.error("Scene planning failed: %s", e)
        return {
            "scenes": [],
            "validation": {"valid": False, "errors": [str(e)], "warnings": []},
            "metadata": {},
        }


def plan_scenes_from_segments(
    segments: List[Dict[str, Any]],
    course_context: str = "",
) -> Dict[str, Any]:
    """Plan scenes from pre-segmented narration (with timing).

    Args:
        segments: List of {text, start_time, end_time} dicts
        course_context: Course title, module info

    Returns:
        Dict with keys: scenes, validation, metadata
    """
    narration_parts = []
    for seg in segments:
        narration_parts.append(seg.get("text", ""))

    narration = "\n".join(narration_parts)

    result = plan_scenes(
        narration=narration,
        course_context=course_context,
        target_duration_s=sum(
            seg.get("end_time", 0) - seg.get("start_time", 0)
            for seg in segments
        ),
    )

    # Map timing from segments to scenes
    if len(result["scenes"]) == len(segments):
        for scene, seg in zip(result["scenes"], segments):
            scene["start_time"] = seg.get("start_time")
            scene["end_time"] = seg.get("end_time")
            if "duration_s" not in scene:
                scene["duration_s"] = seg.get("end_time", 0) - seg.get("start_time", 0)

    return result
