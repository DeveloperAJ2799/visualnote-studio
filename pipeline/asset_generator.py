"""NIM Asset Generator

Uses NVIDIA NIM API to generate infographic images for video scenes.
Takes scene plan visual concepts, generates PNG images via NIM API.
"""
from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import CONFIG

log = logging.getLogger(__name__)

NIM_API_URL = "https://ai.api.nvidia.com/v1/genai/stable-diffusion-xl"

# Style prefix for educational infographics
STYLE_PREFIX = (
    "educational infographic illustration, clean flat design, "
    "dark slate-green background (#16231F), warm chalk white (#F2EFE6) text, "
    "amber (#E8A33D) accent highlights, professional diagram style, "
    "no watermark, high quality, detailed"
)

NEGATIVE_PROMPT = (
    "text, watermark, signature, blurry, low quality, photorealistic, "
    "3d render, photograph, human face, person"
)


def _build_client() -> requests.Session:
    """Build a requests session with NIM API headers."""
    session = requests.Session()
    api_key = CONFIG.nvidia_nim_api_key
    if not api_key:
        raise ValueError("NVIDIA_NIM_API_KEY not set in environment")
    session.headers.update({
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    return session


def generate_infographic(
    prompt: str,
    output_path: Path,
    width: int = 1024,
    height: int = 576,
    num_images: int = 1,
) -> Path:
    """Generate a single infographic image via NIM API.

    Args:
        prompt: Description of what to generate
        output_path: Where to save the PNG
        width: Image width (default 1024)
        height: Image height (default 576, 16:9 ratio)
        num_images: Number of images to generate

    Returns:
        Path to saved image
    """
    client = _build_client()

    full_prompt = f"{STYLE_PREFIX}, {prompt}"
    log.info("Generating asset: %s", prompt[:80])

    payload = {
        "prompt": full_prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "width": width,
        "height": height,
        "num_images_per_prompt": num_images,
        "seed": 42,
    }

    try:
        resp = client.post(NIM_API_URL, json=payload, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("NIM API request failed: %s", e)
        raise

    data = resp.json()

    # Extract base64 image from response
    artifacts = data.get("artifacts", [])
    if not artifacts:
        raise ValueError(f"No artifacts in NIM response: {data}")

    image_b64 = artifacts[0].get("base64", "")
    if not image_b64:
        raise ValueError("Empty base64 in NIM response artifact")

    image_bytes = base64.b64decode(image_b64)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)

    log.info("Saved asset: %s (%d bytes)", output_path, len(image_bytes))
    return output_path


def generate_scene_assets(
    scenes: List[Dict[str, Any]],
    output_dir: Optional[Path] = None,
) -> Dict[int, Path]:
    """Generate infographic images for all scenes in a scene plan.

    Args:
        scenes: List of scene dicts from scene planner
        output_dir: Where to save images (default: remotion_project/public/assets)

    Returns:
        Dict mapping scene_id → image path
    """
    if output_dir is None:
        output_dir = CONFIG.remotion_project_dir / "public" / "assets"

    output_dir.mkdir(parents=True, exist_ok=True)

    asset_map: Dict[int, Path] = {}

    for scene in scenes:
        scene_id = scene.get("scene_id", 0)
        visual_concept = scene.get("visual_concept", "")
        layout = scene.get("layout", "")

        if not visual_concept:
            log.warning("Scene %d has no visual_concept, skipping asset generation", scene_id)
            continue

        # Build a prompt from the visual concept
        prompt = _build_image_prompt(visual_concept, layout, scene.get("title", ""))

        output_path = output_dir / f"scene_{scene_id:03d}.png"

        try:
            generate_infographic(prompt, output_path)
            asset_map[scene_id] = output_path
        except Exception as e:
            log.warning("Failed to generate asset for scene %d: %s", scene_id, e)

    log.info("Generated %d/%d assets", len(asset_map), len(scenes))
    return asset_map


def _build_image_prompt(visual_concept: str, layout: str, title: str) -> str:
    """Build a NIM API prompt from a scene's visual concept.

    Translates the scene planner's visual_concept into an image generation prompt.
    """
    # Clean up the visual concept
    clean = visual_concept.strip().rstrip(".")

    # Add layout-specific guidance
    layout_hints = {
        "big_reveal": "dramatic centered composition, single focal point",
        "split_compare": "side by side comparison layout, two distinct sections",
        "callout_focus": "single highlighted element with annotation arrows",
        "flow_diagram": "connected process diagram with arrows and nodes",
        "definition_card": "key term definition with visual illustration",
        "equation_build": "mathematical formula or equation display",
        "title_card": "title screen with large text and subtitle",
        "stat_beat": "large number statistic with supporting visual",
    }

    hint = layout_hints.get(layout, "educational diagram")

    prompt = f"{clean}, {hint}"
    if title:
        prompt += f", titled '{title}'"

    return prompt


def generate_assets_for_narration(
    narration: str,
    course_context: str = "",
    target_duration_s: float = 30.0,
) -> Dict[int, Path]:
    """Full asset generation: narration → scene plan → images.

    Args:
        narration: Narration text
        course_context: Course title, module info
        target_duration_s: Target duration

    Returns:
        Dict mapping scene_id → image path
    """
    from pipeline.scene_planner import plan_scenes

    log.info("Planning scenes for asset generation...")
    plan = plan_scenes(
        narration=narration,
        course_context=course_context,
        target_duration_s=target_duration_s,
    )

    if not plan["validation"]["valid"]:
        log.error("Scene plan failed: %s", plan["validation"]["errors"])
        return {}

    scenes = plan["scenes"]
    log.info("Generating assets for %d scenes", len(scenes))

    return generate_scene_assets(scenes)
