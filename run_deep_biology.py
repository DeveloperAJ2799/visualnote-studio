"""Run the full VisualNote pipeline with a 10-minute deep-dive manifest,
rendering the final video via HyperFrames.

Usage:
    python run_deep_biology.py
    python run_deep_biology.py --skip-llm    # reuse cached manifest + audio
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from config import CONFIG
from deep_manifest import generate_deep_manifest
from hyperframes_render import render_with_hyperframes
from pipeline.clients.http_client import HTTPClient
from pipeline.ingestion import ingest, load_doc_content
from pipeline.script_gen import load_manifest, save_manifest
from pipeline.tts import synthesize_scene
from pipeline.visuals import render_visuals


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("deep_biology")


PDF_PATH = Path(r"d:\tagmango\Module 2 - The Fundamentals of Building Blocks of Life.pdf")
OUTPUT_MP4 = CONFIG.final_dir / "module2_deep_explanation.mp4"
TARGET_MINUTES = 10
VOICE = "Chloe"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm", action="store_true",
                        help="Reuse cached manifest and audio; only re-render.")
    parser.add_argument("--skip-tts", action="store_true",
                        help="Reuse cached audio files; don't re-synthesize.")
    parser.add_argument("--skip-visuals", action="store_true",
                        help="Skip visual rendering; reuse existing scene images.")
    parser.add_argument("--force-visuals", action="store_true",
                        help="Re-render all scene visuals even if PNGs exist.")
    args = parser.parse_args()

    if not PDF_PATH.exists():
        log.error("PDF not found: %s", PDF_PATH)
        return 1
    if not args.skip_llm and not CONFIG.kilo_api_key:
        log.error("KILO_API_KEY missing in .env")
        return 1
    if not args.skip_tts and not CONFIG.tts_api_key:
        log.error("MIMO_TTS_API_KEY missing in .env")
        return 1

    CONFIG.ensure_dirs()

    log.info("=" * 60)
    log.info("VisualNote Deep Dive: %s", PDF_PATH.name)
    log.info("Target duration: ~%d minutes", TARGET_MINUTES)
    log.info("Renderer: hyperframes")
    log.info("=" * 60)

    log.info("Step 1: ingesting PDF")
    doc_content = load_doc_content()
    if doc_content is None:
        doc_content = ingest(PDF_PATH)
    else:
        log.info("Reusing cached doc_content.json")

    if args.skip_llm:
        manifest = load_manifest()
        if manifest is None:
            log.error("--skip-llm set but no cached manifest at %s",
                      CONFIG.output_dir / "scene_manifest.json")
            return 1
        log.info("Reusing cached manifest: %d scenes", len(manifest["scenes"]))
    log.info("Step 2: building LLM + TTS clients")
    client = HTTPClient(
        kilo_base_url=CONFIG.kilo_base_url,
        kilo_api_key=CONFIG.kilo_api_key,
        kilo_model=CONFIG.kilo_model,
        tts_base_url=CONFIG.tts_base_url,
        tts_api_key=CONFIG.tts_api_key,
        tts_model=CONFIG.tts_model,
        timeout_s=600.0,
    )

    if not args.skip_llm:
        log.info("Step 3: generating %d-min deep-dive manifest", TARGET_MINUTES)
        manifest = generate_deep_manifest(
            doc_content,
            client,
            target_minutes=TARGET_MINUTES,
            max_attempts=3,
        )
        save_manifest(manifest)

    scenes = manifest["scenes"]
    total_words = sum(len(s.get("narration", "").split()) for s in scenes)
    total_hint = sum(int(s.get("duration_hint_s", 0)) for s in scenes)
    log.info(
        "Manifest: %d scenes, %d words, %ds estimated",
        len(scenes), total_words, total_hint,
    )

    if not args.skip_tts:
        log.info("Step 4: synthesizing TTS for each scene")
        for scene in scenes:
            try:
                synthesize_scene(scene, client, voice=VOICE)
            except Exception as exc:
                log.warning("Scene %d TTS failed (%s); silent fallback used",
                            scene["scene_id"], exc)

    if not args.skip_visuals:
        log.info("Step 5: rendering scene visuals (images, diagrams)")
        render_visuals(manifest, doc_content, client=client,
                        force=args.force_visuals)
    else:
        log.info("Step 5: skipped (--skip-visuals)")

    log.info("Step 6: rendering with HyperFrames (engine handles audio mux)")
    try:
        render_with_hyperframes(manifest, OUTPUT_MP4)
    except Exception as exc:
        log.error("HyperFrames render failed: %s", exc)
        return 2

    log.info("=" * 60)
    log.info("DONE: %s (%.1f MB)", OUTPUT_MP4, OUTPUT_MP4.stat().st_size / 1e6)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
