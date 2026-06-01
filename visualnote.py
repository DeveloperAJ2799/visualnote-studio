"""VisualNote orchestrator.

Wires together ingestion, script generation, per-scene visual rendering, TTS,
and final assembly. Honors all CLI flags and supports resume from disk.

Usage:
    python visualnote.py --input notes.pdf --output explainer.mp4 --mock
    python visualnote.py --input notes.pdf --dry-run
    python visualnote.py --input notes.pdf --skip-manim --max-scenes 3
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Optional, Tuple

from tqdm import tqdm

from config import CONFIG
from pipeline.clients.base import MiMoClient, TTSClient
from pipeline.clients.http_client import HTTPClient
from pipeline.clients.mock_client import MockClient
from pipeline.ingestion import ingest, load_doc_content
from pipeline.script_gen import generate_manifest, load_manifest, save_manifest
from pipeline.manim_gen import render_manim_scene
from pipeline.html_gen import render_html_frame
from pipeline.image_fetcher import render_image_overlay, render_title_card
from pipeline.tts import synthesize_scene
from pipeline.assembler import assemble

log = logging.getLogger("visualnote")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    warnings.filterwarnings(
        "ignore",
        message=r".*bytes wanted but 0 bytes read.*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r".*Using the last valid frame instead.*",
        category=UserWarning,
    )


def make_clients(args: argparse.Namespace) -> Tuple[MiMoClient, TTSClient]:
    """Construct the LLM and TTS clients per --mock / env config."""
    use_mock = bool(args.mock) or CONFIG.use_mock
    if use_mock:
        log.info("Client: MockClient (no API spend)")
        return MockClient(), MockClient()
    if not CONFIG.mimo_api_key:
        log.error(
            "MIMO_USE_MOCK is false but MIMO_API_KEY is empty. "
            "Set it in .env or pass --mock."
        )
        sys.exit(2)
    log.info("Client: HTTPClient (base=%s, model=%s)", CONFIG.mimo_base_url, CONFIG.mimo_model)
    llm = HTTPClient(
        base_url=CONFIG.mimo_base_url,
        api_key=CONFIG.mimo_api_key,
        model=CONFIG.mimo_model,
        tts_base_url=CONFIG.tts_base_url,
        tts_api_key=CONFIG.tts_api_key,
        tts_model=CONFIG.tts_model,
    )
    return llm, llm


def step_ingest(args: argparse.Namespace) -> dict:
    if args.force_manifest:
        log.info("Ingest: --force-manifest requested; re-running ingestion")
    cached = load_doc_content()
    if cached and not args.force_manifest:
        log.info("Ingest: reusing cached doc_content.json")
        return cached
    log.info("Ingest: parsing %s", args.input)
    return ingest(args.input)


def step_manifest(
    doc_content: dict,
    llm: MiMoClient,
    args: argparse.Namespace,
) -> dict:
    if not args.force_manifest:
        cached = load_manifest()
        if cached:
            log.info(
                "Manifest: reusing cached scene_manifest.json (%d scenes)",
                len(cached.get("scenes", [])),
            )
            if args.max_scenes is not None and len(cached.get("scenes", [])) > args.max_scenes:
                cached["scenes"] = cached["scenes"][: args.max_scenes]
                cached["total_scenes"] = len(cached["scenes"])
            return cached
    log.info("Manifest: generating via LLM")
    manifest = generate_manifest(doc_content, llm, max_scenes=args.max_scenes)
    save_manifest(manifest)
    return manifest


def step_render_scenes(
    manifest: dict,
    doc_content: dict,
    llm: MiMoClient,
    args: argparse.Namespace,
) -> None:
    scenes = manifest.get("scenes", [])
    log.info("Render: %d scenes to process", len(scenes))
    for scene in tqdm(scenes, desc="Scenes", unit="scene"):
        sid = scene["scene_id"]
        vt = scene.get("visual_type")

        if vt == "manim_animation" and not args.skip_manim:
            try:
                render_manim_scene(scene, llm)
            except Exception as exc:
                log.warning("Scene %d Manim render failed: %s; using title card", sid, exc)
                render_title_card(scene)
        elif vt == "manim_animation" and args.skip_manim:
            render_title_card(scene)
        elif vt == "html_frame":
            try:
                render_html_frame(scene, llm)
            except Exception as exc:
                log.warning("Scene %d HTML frame failed: %s; using title card", sid, exc)
                render_title_card(scene)
        elif vt == "image_overlay":
            render_image_overlay(scene, doc_content)
        elif vt == "title_card":
            render_title_card(scene)
        else:
            log.warning("Scene %d: unknown visual_type=%r; using title card", sid, vt)
            render_title_card(scene)


def step_synthesize(
    manifest: dict,
    tts: TTSClient,
    args: argparse.Namespace,
) -> None:
    scenes = manifest.get("scenes", [])
    log.info("TTS: synthesizing %d scenes (voice=%s)", len(scenes), args.voice)
    for scene in tqdm(scenes, desc="TTS", unit="scene"):
        try:
            synthesize_scene(scene, tts, voice=args.voice)
        except Exception as exc:
            log.warning("Scene %d TTS failed: %s; emitting silent fallback", scene["scene_id"], exc)
            synthesize_scene({"scene_id": scene["scene_id"], "narration": "."}, tts, voice=args.voice)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visualnote",
        description=(
            "VisualNote — convert a study document (PDF/PPTX/DOCX) into a "
            "narrated explainer video with Manim animations and HTML frames."
        ),
    )
    parser.add_argument("--input", "-i", required=True, help="Path to the input document.")
    parser.add_argument(
        "--output", "-o",
        default=str(CONFIG.final_dir / "explainer.mp4"),
        help="Path for the final MP4.",
    )
    parser.add_argument("--voice", default=CONFIG.tts_voice, help="TTS voice preset.")
    parser.add_argument(
        "--resolution", choices=["720p", "1080p"], default=CONFIG.default_resolution,
    )
    parser.add_argument("--max-scenes", type=int, default=None)
    parser.add_argument("--skip-manim", action="store_true")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-manifest", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_argparser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    log.info("=" * 60)
    log.info("VisualNote starting")
    log.info("  input:        %s", args.input)
    log.info("  output:       %s", args.output)
    log.info("  resolution:   %s", args.resolution)
    log.info("  voice:        %s", args.voice)
    log.info("  mock mode:    %s", bool(args.mock) or CONFIG.use_mock)
    log.info("  dry run:      %s", args.dry_run)
    log.info("=" * 60)

    input_path = Path(args.input)
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        return 2

    llm, tts = make_clients(args)
    doc_content = step_ingest(args)
    manifest = step_manifest(doc_content, llm, args)
    if args.dry_run:
        log.info("Dry run: stopping after manifest (%d scenes)", len(manifest["scenes"]))
        log.info("Manifest: %s", CONFIG.output_dir / "scene_manifest.json")
        return 0

    step_render_scenes(manifest, doc_content, llm, args)
    step_synthesize(manifest, tts, args)

    out = Path(args.output)
    assemble(manifest, out)

    log.info("=" * 60)
    log.info("Done. Final video: %s", out)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
