"""Run the VisualNote deep-dive pipeline on any PDF, rendering the final
video via HyperFrames. The pipeline is PDF-agnostic — pass any PDF via
--pdf, or drop one in the project root and let it auto-discover.

Usage:
    python run_deep_biology.py                            # auto: first *.pdf in project root
    python run_deep_biology.py --pdf "Module 3.pdf"       # specific PDF
    python run_deep_biology.py --out "videos/m3.mp4"      # custom output
    python run_deep_biology.py --skip-llm --skip-tts      # reuse cached manifest + audio
    python run_deep_biology.py --target-minutes 5         # shorter video
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


PDF_PATH: Path | None = None  # default: first *.pdf found in project_root
OUTPUT_DIR = CONFIG.final_dir
TARGET_MINUTES = 10
VOICE = "Chloe"


def _default_pdf() -> Path | None:
    """Return the first PDF in the project root, or None if there are no PDFs."""
    candidates = sorted(CONFIG.project_root.glob("*.pdf"))
    return candidates[0] if candidates else None


def _output_mp4_for(pdf_path: Path) -> Path:
    """Derive a stable output filename from the PDF stem, e.g.
    'Module 2 - The Fundamentals of Building Blocks of Life.pdf'
        -> 'module_2_the_fundamentals_of_building_blocks_of_life_deep_explanation.mp4'
    """
    stem = pdf_path.stem.lower()
    safe = "".join(c if c.isalnum() else "_" for c in stem)
    safe = "_".join(part for part in safe.split("_") if part)
    return OUTPUT_DIR / f"{safe}_deep_explanation.mp4"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the VisualNote deep-dive pipeline on any PDF.",
    )
    parser.add_argument("--pdf", type=Path, default=None,
                        help="Path to input PDF file. Defaults to the first "
                             "*.pdf found in the project root.")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output MP4 path. Defaults to "
                             "output/final/<pdf_stem>_deep_explanation.mp4.")
    parser.add_argument("--target-minutes", type=int, default=TARGET_MINUTES,
                        help=f"Target video length in minutes (default: {TARGET_MINUTES}).")
    parser.add_argument("--voice", type=str, default=VOICE,
                        help=f"TTS voice (default: {VOICE}).")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Reuse cached manifest and audio; only re-render.")
    parser.add_argument("--skip-tts", action="store_true",
                        help="Reuse cached audio files; don't re-synthesize.")
    parser.add_argument("--skip-visuals", action="store_true",
                        help="Skip visual rendering; reuse existing scene images.")
    parser.add_argument("--force-visuals", action="store_true",
                        help="Re-render all scene visuals even if PNGs exist.")
    parser.add_argument("--no-council", action="store_true",
                        help="Skip the 5-member council; use single-LLM legacy path.")
    parser.add_argument("--council-fast", action="store_true",
                        help="Council with Round 2 reviews skipped (3 calls, "
                             "faster but lower quality).")
    parser.add_argument("--council-config", type=Path, default=None,
                        help="Path to a custom council_config.json. Defaults to "
                             "pipeline/council/council_config.json. Lets you swap "
                             "the entire council (members, models, system prompts, "
                             "phases) without touching Python.")
    args = parser.parse_args()

    # Resolve PDF (CLI override -> default discovery)
    pdf_arg = args.pdf or _default_pdf()
    if pdf_arg is None:
        log.error("No PDF specified and none found in %s", CONFIG.project_root)
        return 1
    pdf_path = pdf_arg.resolve()
    if not pdf_path.exists():
        log.error("PDF not found: %s", pdf_path)
        return 1

    # Resolve output path (CLI override -> derive from PDF stem)
    output_mp4 = args.out.resolve() if args.out else _output_mp4_for(pdf_path)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    if not args.skip_llm and not CONFIG.kilo_api_key:
        log.error("KILO_API_KEY missing in .env")
        return 1
    if not args.skip_tts and not CONFIG.tts_api_key:
        log.error("MIMO_TTS_API_KEY missing in .env")
        return 1

    CONFIG.ensure_dirs()

    log.info("=" * 60)
    log.info("VisualNote Deep Dive: %s", pdf_path.name)
    log.info("Target duration: ~%d minutes", args.target_minutes)
    log.info("Output: %s", output_mp4)
    log.info("Renderer: hyperframes")
    log.info("=" * 60)

    log.info("Step 1: ingesting PDF")
    doc_content = load_doc_content()
    if doc_content is None:
        doc_content = ingest(pdf_path)
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
        log.info("Step 3: generating %d-min deep-dive manifest", args.target_minutes)
        if args.no_council:
            log.info("Council: disabled (--no-council); using single-LLM path")
        elif args.council_fast:
            log.info("Council: fast mode (Round 2 reviews skipped)")
        else:
            log.info("Council: full 5-member deliberation")
        if args.council_config:
            log.info("Council config override: %s", args.council_config)
        manifest = generate_deep_manifest(
            doc_content,
            client,
            target_minutes=args.target_minutes,
            max_attempts=3,
            use_council=not args.no_council,
            fast=args.council_fast,
            council_config=args.council_config,
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
                synthesize_scene(scene, client, voice=args.voice)
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
        render_with_hyperframes(manifest, output_mp4)
    except Exception as exc:
        log.error("HyperFrames render failed: %s", exc)
        return 2

    log.info("=" * 60)
    log.info("DONE: %s (%.1f MB)", output_mp4, output_mp4.stat().st_size / 1e6)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
