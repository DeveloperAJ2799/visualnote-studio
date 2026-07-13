"""Test full pipeline: narration → scene plan → LLM code → render."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.scene_planner import plan_scenes
from pipeline.render_motion import render_from_narration

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def test_scene_planner():
    """Test scene planning step only (no render)."""
    narration = (
        "Enzymes are biological catalysts that speed up chemical reactions in living organisms. "
        "Each enzyme has a specific three-dimensional shape that determines its function. "
        "The active site is the region where substrate molecules bind to the enzyme. "
        "The lock and key model explains how substrates fit precisely into the active site. "
        "When the substrate binds, the enzyme-substrate complex forms temporarily. "
        "After the reaction completes, the products are released and the enzyme is reused."
    )

    log.info("Testing scene planner...")
    result = plan_scenes(
        narration=narration,
        course_context="Module 4 - Enzymes",
        target_duration_s=30,
    )

    log.info("Validation: %s", result["validation"])

    if result["validation"]["errors"]:
        log.error("Errors: %s", result["validation"]["errors"])
        return False

    for scene in result["scenes"]:
        log.info(
            "Scene %d [%s]: %s (%.0fs)",
            scene["scene_id"],
            scene.get("layout", "?"),
            scene.get("visual_concept", "?")[:60],
            scene.get("duration_s", 0),
        )

    log.info("Metadata: %s", result["metadata"])
    return True


def test_full_pipeline():
    """Test the complete pipeline: narration → video."""
    narration = (
        "Enzymes are biological catalysts that speed up chemical reactions. "
        "Each enzyme has a specific shape with an active site for substrate binding."
    )

    output = Path("output/final/test_full_pipeline.mp4")
    log.info("Testing full pipeline...")

    result_path = render_from_narration(
        narration=narration,
        output_path=output,
        course_context="Module 4 - Enzymes",
        target_duration_s=10,
    )

    log.info("Output: %s", result_path)
    return result_path.exists()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        success = test_full_pipeline()
    else:
        success = test_scene_planner()
    sys.exit(0 if success else 1)
