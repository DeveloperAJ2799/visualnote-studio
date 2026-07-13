"""Motion Graphics Generator

Uses LLM to generate Remotion React code for educational video scenes.
Takes narration text + document context, returns valid JSX.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import CONFIG
from pipeline.clients.http_client import HTTPClient
from pipeline.motion_prompt import get_system_prompt, get_component_api_reference

log = logging.getLogger(__name__)


def _build_client() -> HTTPClient:
    """Build the HTTP client for LLM calls."""
    return HTTPClient(
        kilo_base_url=CONFIG.kilo_base_url,
        kilo_api_key=CONFIG.kilo_api_key,
        kilo_model=CONFIG.kilo_model,
        tts_base_url=CONFIG.tts_base_url,
        tts_api_key=CONFIG.tts_api_key,
        tts_model=CONFIG.tts_model,
        timeout_s=180.0,
    )


def _extract_code_block(response: str) -> str:
    """Extract the first code block from LLM response."""
    # Try to find ```tsx or ```jsx code blocks
    patterns = [
        r"```tsx\s*\n(.*?)```",
        r"```jsx\s*\n(.*?)```",
        r"```typescript\s*\n(.*?)```",
        r"```javascript\s*\n(.*?)```",
        r"```react\s*\n(.*?)```",
        r"```\s*\n(.*?)```",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    # If no code block found, try to extract the component definition
    # Look for export default function or export const
    component_match = re.search(
        r"(export\s+default\s+function\s+\w+.*?)(?:\n\n|\Z)",
        response,
        re.DOTALL,
    )
    if component_match:
        return component_match.group(1).strip()
    
    # Last resort: return the whole response (might be raw JSX)
    return response.strip()


def _validate_jsx(code: str) -> Dict[str, Any]:
    """Basic validation of generated JSX code."""
    errors = []
    warnings = []

    # Check for required imports
    if "from \"react\"" not in code and "from 'react'" not in code:
        errors.append("Missing React import")

    if "from \"remotion\"" not in code and "from 'remotion'" not in code:
        errors.append("Missing Remotion import")

    if "useCurrentFrame" not in code:
        warnings.append("Missing useCurrentFrame hook")

    # Accept either ThreeScene or ChalkBackground as root wrapper
    has_three = "ThreeScene" in code
    has_chalk = "ChalkBackground" in code
    if not has_three and not has_chalk:
        warnings.append("Missing ThreeScene or ChalkBackground wrapper")

    # Check for anti-patterns
    if "bullet" in code.lower() and ("list" in code.lower() or "<li" in code.lower()):
        errors.append("Contains bullet list (IGWANI anti-pattern)")

    if "#000000" in code or "#FFFFFF" in code:
        warnings.append("Uses pure black/white (should use theme tokens)")

    # Check for export default
    if "export default" not in code:
        warnings.append("Missing export default")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def generate_motion_scene(
    narration: str,
    context: str = "",
    scene_number: int = 1,
    duration_frames: int = 180,
    max_retries: int = 2,
    previous_layouts: Optional[List[str]] = None,
    asset_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a Remotion + Three.js scene component from narration text.

    Args:
        narration: The narration text for this scene
        context: Additional context (course title, previous scenes, etc.)
        scene_number: Scene number for naming
        duration_frames: Expected duration in frames
        max_retries: Number of retry attempts on failure
        previous_layouts: Layout patterns used in prior scenes (for variety)
        asset_path: Path to generated infographic image for this scene

    Returns:
        Dict with keys: code, scene_name, validation, metadata
    """
    client = _build_client()

    system_prompt = get_system_prompt()
    component_api = get_component_api_reference()

    variety_note = ""
    if previous_layouts:
        variety_note = (
            f"\nPREVIOUS SCENE LAYOUTS (DO NOT repeat these for this scene): "
            f"{', '.join(previous_layouts[-3:])}\n"
            f"Choose a DIFFERENT layout pattern for this scene.\n"
        )

    asset_note = ""
    if asset_path:
        asset_note = (
            f"\nAVAILABLE IMAGE ASSET for this scene: {asset_path}\n"
            f"Use this image on an <ImagePlane> in your 3D scene.\n"
        )

    user_prompt = f"""Generate a Remotion + Three.js scene component for this narration:

Narration: {narration}

Context: {context}

Duration: {duration_frames} frames ({duration_frames / 30:.1f} seconds)
{variety_note}{asset_note}
{component_api}

Requirements:
1. Create a single React component using ThreeScene as root wrapper
2. Use Three.js 3D components (ImagePlane, CameraRig, Text3D, ParticleField, GlowMesh)
3. Include <ParticleField /> for atmospheric depth
4. Include <CameraRig /> for camera movement — no static cameras
5. No bullet lists — visual concepts only
6. Spring animations for entrances
7. Export default the component function
8. Name the function Scene{scene_number:03d}

Generate the complete TSX code:"""
    
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            raw_code = client._post_chat_kilo(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                json_mode=False,
                temperature=0.7,
            )
            
            if not raw_code:
                last_error = "Empty LLM response"
                if attempt < max_retries:
                    log.warning("Scene %d attempt %d: empty response, retrying", scene_number, attempt + 1)
                    continue
                return {
                    "code": "",
                    "scene_name": f"Scene{scene_number:03d}",
                    "validation": {"valid": False, "errors": [last_error], "warnings": []},
                    "metadata": {"narration": narration, "duration_frames": duration_frames},
                }
            
            # Extract code from response
            code = _extract_code_block(raw_code)
            
            # Ensure proper function name
            code = re.sub(
                r"export\s+default\s+function\s+\w+",
                f"export default function Scene{scene_number:03d}",
                code,
            )
            
            # Validate
            validation = _validate_jsx(code)
            
            # Retry if critical errors found
            if not validation["valid"] and attempt < max_retries:
                log.warning("Scene %d attempt %d validation failed: %s, retrying",
                           scene_number, attempt + 1, validation["errors"])
                last_error = validation["errors"]
                continue
            
            scene_name = f"Scene{scene_number:03d}"
            
            return {
                "code": code,
                "scene_name": scene_name,
                "validation": validation,
                "metadata": {
                    "narration": narration,
                    "duration_frames": duration_frames,
                    "context": context,
                },
            }
            
        except Exception as e:
            last_error = str(e)
            log.error("Scene %d attempt %d failed: %s", scene_number, attempt + 1, e)
            if attempt < max_retries:
                continue
            return {
                "code": "",
                "scene_name": f"Scene{scene_number:03d}",
                "validation": {"valid": False, "errors": [last_error], "warnings": []},
                "metadata": {"narration": narration, "duration_frames": duration_frames},
            }
    
    # Should not reach here, but just in case
    return {
        "code": "",
        "scene_name": f"Scene{scene_number:03d}",
        "validation": {"valid": False, "errors": [str(last_error)], "warnings": []},
        "metadata": {"narration": narration, "duration_frames": duration_frames},
    }


def generate_motion_scenes(
    scenes: list[Dict[str, Any]],
    course_context: str = "",
    asset_map: Optional[Dict[int, str]] = None,
) -> list[Dict[str, Any]]:
    """Generate motion graphics for multiple scenes.

    Args:
        scenes: List of scene dicts with narration, duration_hint_s, etc.
        course_context: Overall course context
        asset_map: Dict mapping scene_id → image file path (from asset generator)

    Returns:
        List of generated scene dicts with code
    """
    results = []
    previous_layouts: List[str] = []

    for i, scene in enumerate(scenes):
        scene_num = i + 1
        narration = scene.get("narration", "")
        duration_s = scene.get("duration_hint_s", 15)
        duration_frames = int(duration_s * 30)
        scene_id = scene.get("scene_id", scene_num)

        log.info("Generating motion for scene %d/%d: %s", scene_num, len(scenes), scene.get("title", ""))

        # Get asset path for this scene
        asset_path = None
        if asset_map and scene_id in asset_map:
            # Use the public URL path for Remotion
            asset_filename = Path(asset_map[scene_id]).name
            asset_path = f"/assets/{asset_filename}"

        result = generate_motion_scene(
            narration=narration,
            context=course_context,
            scene_number=scene_num,
            duration_frames=duration_frames,
            previous_layouts=previous_layouts,
            asset_path=asset_path,
        )
        
        result["scene_id"] = scene.get("scene_id", scene_num)
        result["title"] = scene.get("title", "")

        # Track layout for variety in next scenes
        layout = scene.get("layout", "flow_diagram")
        previous_layouts.append(layout)

        if result["validation"]["valid"]:
            log.info("  ✓ Scene %d generated successfully", scene_num)
        else:
            log.warning("  ✗ Scene %d has errors: %s", scene_num, result["validation"]["errors"])
        
        results.append(result)
    
    return results
