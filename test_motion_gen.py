"""Test script for motion graphics generation.

Generates a single scene from narration and renders it.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.motion_gen import generate_motion_scene
from pipeline.render_motion import (
    _write_scene_file,
    _update_course_reel,
    _copy_audio_files,
    _update_remotion_props,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def test_single_scene():
    """Generate and render a single test scene."""
    narration = (
        "Enzymes are biological catalysts that speed up chemical reactions. "
        "They have a specific 3D shape with an active site where substrates bind. "
        "The lock and key model explains how substrates fit perfectly into the active site."
    )
    
    log.info("Generating motion scene...")
    result = generate_motion_scene(
        narration=narration,
        context="Module 4 - Enzymes",
        scene_number=1,
        duration_frames=180,
    )
    
    if not result["validation"]["valid"]:
        log.error("Validation failed: %s", result["validation"]["errors"])
        return False
    
    log.info("Validation passed. Warnings: %s", result["validation"]["warnings"])
    log.info("Generated code:\n%s", result["code"][:500] + "...")
    
    # Write the scene file
    scene_path = _write_scene_file(result["scene_name"], result["code"])
    log.info("Wrote scene to: %s", scene_path)
    
    # Update CourseReel.tsx
    _update_course_reel([result])
    
    # Create minimal props
    import json
    props = {
        "course_title": "Test Motion Graphics",
        "fps": 30,
        "scenes": [{
            "scene_id": 1,
            "template": "dynamic",
            "narration": narration,
            "fields": {},
            "durationInFrames": 180,
            "annotations": [],
        }],
    }
    
    props_path = Path("output/remotion_props_test.json")
    props_path.parent.mkdir(parents=True, exist_ok=True)
    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)
    
    log.info("Wrote test props to: %s", props_path)
    log.info("Scene generated successfully!")
    
    # Print the code for review
    print("\n" + "=" * 80)
    print("GENERATED CODE:")
    print("=" * 80)
    print(result["code"])
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    success = test_single_scene()
    sys.exit(0 if success else 1)
