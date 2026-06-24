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
import logging
import sys
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

try:
    from hyperframes_render import render_with_hyperframes
    _HYPERFRAMES_AVAILABLE = True
except Exception as _hf_exc:  # pragma: no cover
    render_with_hyperframes = None  # type: ignore
    _HYPERFRAMES_AVAILABLE = False
    _HYPERFRAMES_IMPORT_ERROR = _hf_exc

log = logging.getLogger("visualnote")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Moviepy clip-extension warnings are now suppressed at import time inside
    # `pipeline.assembler` so they apply whether the assembler is called from
    # this CLI or imported directly by a helper script.


def make_clients(args: argparse.Namespace) -> Tuple[MiMoClient, TTSClient]:
    """Construct the LLM and TTS clients per --mock / env config."""
    use_mock = bool(args.mock) or CONFIG.use_mock
    if use_mock:
        log.info("Client: MockClient (no API spend)")
        return MockClient(), MockClient()
    missing = []
    if not CONFIG.kilo_api_key:
        missing.append("KILO_API_KEY")
    if not CONFIG.tts_api_key:
        missing.append("MIMO_TTS_API_KEY")
    if missing:
        log.error(
            "MIMO_USE_MOCK is false but the following env vars are empty: %s. "
            "Set them in .env or pass --mock.",
            ", ".join(missing),
        )
        sys.exit(2)
    log.info(
        "LLM: Kilo gateway base=%s model=%s",
        CONFIG.kilo_base_url, CONFIG.kilo_model,
    )
    log.info(
        "TTS: MiMo base=%s model=%s voice=%s",
        CONFIG.tts_base_url, CONFIG.tts_model, CONFIG.tts_voice,
    )
    llm = HTTPClient(
        kilo_base_url=CONFIG.kilo_base_url,
        kilo_api_key=CONFIG.kilo_api_key,
        kilo_model=CONFIG.kilo_model,
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
            from deep_manifest import _assign_frame_styles
            cached = _assign_frame_styles(cached)
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
    from pipeline.tts import _silent_wav_for_text

    scenes = manifest.get("scenes", [])
    log.info("TTS: synthesizing %d scenes (voice=%s)", len(scenes), args.voice)
    for scene in tqdm(scenes, desc="TTS", unit="scene"):
        try:
            synthesize_scene(scene, tts, voice=args.voice)
        except Exception as exc:
            log.warning("Scene %d TTS failed: %s; emitting silent fallback", scene["scene_id"], exc)
            # Write a silent WAV so the assembler always has audio for every
            # scene.  The duration is estimated from the narration word count.
            wav_path = (
                CONFIG.scenes_dir / f"scene_{scene['scene_id']:03d}_audio.wav"
            )
            narration = scene.get("narration") or "."
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            wav_path.write_bytes(_silent_wav_for_text(narration))


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
    parser.add_argument(
        "--renderer",
        choices=["moviepy", "hyperframes"],
        default="moviepy",
        help="Final-assembly renderer: moviepy (default) or hyperframes (HTML composition).",
    )
    parser.add_argument(
        "--agent", action="store_true",
        help="Hand off composition authoring to the HyperFrames agent skill "
             "(writes BRIEF.md, invokes claude/codex/gemini). Skips the Python "
             "manifest + TTS + render pipeline; the agent does it all.",
    )
    parser.add_argument(
        "--print-brief", action="store_true",
        help="With --agent, just write BRIEF.md and print its path (don't invoke the agent).",
    )
    parser.add_argument(
        "--target-minutes", type=int, default=10,
        help="Target video length in minutes (used by --agent).",
    )
    parser.add_argument(
        "--intent", default="10-minute deep explanation",
        help="Render intent (used by --agent).",
    )
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
    log.info("  agent mode:   %s", args.agent)
    log.info("=" * 60)

    input_path = Path(args.input)
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        return 2

    if args.agent:
        from agent_render import build_brief, invoke_agent, write_brief, _detect_agent
        project_dir = CONFIG.output_dir / "hyperframes_project"
        project_dir.mkdir(parents=True, exist_ok=True)
        brief = build_brief(
            input_path, args.intent, Path(args.output),
            target_minutes=args.target_minutes,
        )
        brief_path = write_brief(brief, project_dir)
        log.info("Wrote brief: %s", brief_path)
        if args.print_brief:
            print(brief_path)
            return 0
        agent = _detect_agent()
        if not agent:
            log.error("No agent CLI on PATH (claude/codex/gemini/cursor/kilo). "
                      "Re-run with --print-brief to get the brief path.")
            return 2
        return invoke_agent(agent, brief_path, project_dir)

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
    if args.renderer == "hyperframes":
        if not _HYPERFRAMES_AVAILABLE:
            log.error(
                "HyperFrames renderer requested but import failed: %s. "
                "Run `npx --yes hyperframes --version` to verify install.",
                _HYPERFRAMES_IMPORT_ERROR,
            )
            return 3
        log.info("Renderer: hyperframes (HTML composition)")
        render_with_hyperframes(manifest, out)
    else:
        log.info("Renderer: moviepy (default)")
        assemble(manifest, out)

    log.info("=" * 60)
    log.info("Done. Final video: %s", out)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
