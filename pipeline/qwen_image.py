"""Qwen Image generator via NVIDIA NIM API.

Generates educational diagrams and illustrations for each scene
using the Qwen-Image text-to-image model.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/models/qwen/qwen-image/generations"
NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "")

# Scene-specific prompt templates for biology education
SCENE_PROMPTS = {
    "cell_structure": (
        "Educational scientific diagram of {topic}, labeled parts, "
        "clean white background, professional biology textbook style, "
        "high detail, accurate scientific illustration"
    ),
    "molecular": (
        "Detailed molecular diagram showing {topic}, "
        "colorful atoms, chemical bonds, scientific visualization, "
        "educational poster style, clear labels"
    ),
    "process": (
        "Step-by-step biological process diagram of {topic}, "
        "arrows showing flow, numbered stages, educational infographic, "
        "clean design, biology textbook illustration"
    ),
    "comparison": (
        "Side-by-side comparison diagram of {topic}, "
        "labeled differences, educational chart, scientific illustration, "
        "clear visual distinction"
    ),
    "default": (
        "Educational biology illustration of {topic}, "
        "scientific diagram, labeled parts, professional quality, "
        "textbook style, clear and informative"
    ),
}


def generate_scene_image(
    scene: dict,
    out_path: Path,
    api_key: Optional[str] = None,
    *,
    width: int = 1920,
    height: int = 1080,
    max_retries: int = 2,
) -> Optional[Path]:
    """Generate an image for a scene using Qwen Image via NVIDIA NIM.

    Args:
        scene: Scene dict with title, narration, visual_type, etc.
        out_path: Where to save the generated PNG.
        api_key: NVIDIA NIM API key. Falls back to env var.
        width: Output image width.
        height: Output image height.
        max_retries: Number of retry attempts.

    Returns:
        Path to saved image, or None on failure.
    """
    api_key = api_key or NIM_API_KEY
    if not api_key:
        log.warning("No NVIDIA NIM API key; skipping image generation for scene %d",
                     scene.get("scene_id", 0))
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        log.info("Scene %d: image already exists, skipping", scene.get("scene_id", 0))
        return out_path

    topic = scene.get("title", "biology concept")
    visual_type = scene.get("visual_type", "default")
    narration = scene.get("narration", "")[:200]

    # Build prompt based on visual type
    template = SCENE_PROMPTS.get(visual_type, SCENE_PROMPTS["default"])
    prompt = template.format(topic=topic)
    if narration:
        prompt += f". Key concept: {narration}"

    # Determine aspect ratio from dimensions
    if width > height:
        aspect_ratio = "16:9"
    elif height > width:
        aspect_ratio = "9:16"
    else:
        aspect_ratio = "1:1"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "prompt": prompt,
        "negative_prompt": "blurry, low quality, distorted, ugly, watermark, text overlay",
        "steps": 30,
        "seed": -1,
        "guidance": 3.5,
        "aspect_ratio": aspect_ratio,
        "image_format": "png",
        "quality": 90,
        "base64": True,
    }

    for attempt in range(1, max_retries + 1):
        try:
            log.info("Scene %d: generating image (attempt %d)", scene.get("scene_id", 0), attempt)
            resp = requests.post(NIM_ENDPOINT, headers=headers, json=payload, timeout=120)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 10))
                log.warning("Rate limited; waiting %ds", wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            # Extract base64 image from response
            image_b64 = None
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if "b64_json" in item:
                        image_b64 = item["b64_json"]
                        break
                    elif "url" in item:
                        # Download from URL
                        img_resp = requests.get(item["url"], timeout=60)
                        img_resp.raise_for_status()
                        out_path.write_bytes(img_resp.content)
                        log.info("Scene %d: image saved from URL to %s",
                                 scene.get("scene_id", 0), out_path)
                        return out_path
            elif "image" in data:
                # Segmind-style response
                image_b64 = data["image"]

            if image_b64:
                img_bytes = base64.b64decode(image_b64)
                out_path.write_bytes(img_bytes)
                log.info("Scene %d: image saved to %s (%d bytes)",
                         scene.get("scene_id", 0), out_path, len(img_bytes))
                return out_path

            log.warning("Scene %d: no image in API response", scene.get("scene_id", 0))

        except requests.exceptions.RequestException as exc:
            log.warning("Scene %d: API error (attempt %d): %s",
                        scene.get("scene_id", 0), attempt, str(exc)[:200])
            if attempt < max_retries:
                time.sleep(5 * attempt)

    log.error("Scene %d: failed to generate image after %d attempts",
              scene.get("scene_id", 0), max_retries)
    return None


def generate_images_for_manifest(
    manifest: dict,
    api_key: Optional[str] = None,
) -> list[Path]:
    """Generate images for all scenes in a manifest.

    Returns list of successfully generated image paths.
    """
    from config import CONFIG

    api_key = api_key or NIM_API_KEY
    paths: list[Path] = []

    for scene in manifest.get("scenes", []):
        scene_id = scene.get("scene_id", 0)
        out_path = CONFIG.scenes_dir / f"scene_{scene_id:03d}_gen.png"

        # Skip if already generated
        if out_path.exists():
            paths.append(out_path)
            continue

        # Only generate for scenes that would benefit from AI images
        visual_type = scene.get("visual_type", "title_card")
        if visual_type in ("manim_animation", "html_frame"):
            result = generate_scene_image(scene, out_path, api_key)
            if result:
                paths.append(result)

    return paths
