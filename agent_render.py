"""Agent-driven render wrapper.

Generates a BRIEF.md describing the input document + intent and hands off to
the HyperFrames skill for composition authoring. The agent (Claude Code,
Cursor, Codex, Gemini CLI) reads the brief, writes a HyperFrames composition,
and invokes `hyperframes render`.

This is the non-interactive entry point. For interactive use, the user runs
the agent directly (the brief is regenerated each call to keep the agent's
context fresh).

Usage:
    python agent_render.py --input paper.pdf --output out.mp4 --intent "10-min deep explainer"
    python agent_render.py --print-brief --input paper.pdf --intent "10-min deep explainer"
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from config import CONFIG
from pipeline.ingestion import ingest, load_doc_content

log = logging.getLogger(__name__)


def _detect_agent() -> Optional[str]:
    """Return the name of the first available agent CLI, or None."""
    candidates = [
        ("claude", "Claude Code"),
        ("codex", "OpenAI Codex"),
        ("gemini", "Gemini CLI"),
        ("cursor", "Cursor"),
        ("kilo", "Kilo Code"),
    ]
    for bin_name, label in candidates:
        if shutil.which(bin_name):
            return bin_name
    return None


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[-\s]+", "-", s)
    return s[:60] or "brief"


def build_brief(
    input_pdf: Path,
    intent: str,
    output: Path,
    *,
    target_minutes: int = 10,
) -> str:
    """Build the BRIEF.md the agent will consume."""
    doc = load_doc_content()
    if doc is None:
        log.info("Ingesting %s for the brief…", input_pdf)
        doc = ingest(input_pdf)

    title = doc.get("document_title") or input_pdf.stem
    sections = doc.get("sections", [])
    section_lines: list[str] = []
    for s in sections[:30]:
        heading = s.get("heading") or ""
        if heading:
            section_lines.append(f"  - {heading}")
    if len(sections) > 30:
        section_lines.append(f"  - …({len(sections) - 30} more sections)")

    raw_excerpt = (doc.get("raw_text") or "")[:6000]
    images = doc.get("image_index") or []
    image_lines = [f"  - {im.get('path', '?')}" for im in images[:12]]

    scenes_target = max(15, target_minutes * 2)
    word_target = target_minutes * 140

    brief = f"""# VisualNote Brief — {title}

## Intent
{intent}

## Input
- PDF: `{input_pdf}`
- Pages: {doc.get('page_count', '?')}
- Title: {title}
- Target duration: ~{target_minutes} minutes
- Target scene count: ~{scenes_target} scenes
- Target narration: ~{word_target} words at 140 WPM

## Document structure (top headings)
{chr(10).join(section_lines) if section_lines else '  (no headings detected)'}

## Extracted images ({len(images)} total)
{chr(10).join(image_lines) if image_lines else '  (none)'}

## Source excerpt (first ~6000 chars)
```
{raw_excerpt}
```

## What to build

Author a single HyperFrames HTML composition in
`{CONFIG.output_dir / 'hyperframes_project'}/index.html` that renders a
{intent} for the document above. The composition should:

1. Open with a 3-4 second title card (module title + subtitle).
2. Walk through the document in source order, devoting one scene per
   heading or sub-topic.
3. Use the extracted PDF page images (or `image_index` entries above) as
   background visuals for image_overlay scenes. Prefer
   `output/assets/extracted/img_p*`.
4. End with a recap / 5-takeaways scene.

## HyperFrames contract (must follow)

- Composition root: first element with `data-width="1920"` and
  `data-height="1080"`. Give it a `data-composition-id` (e.g. the slug
  `{_slug(title)}`).
- Every timed element must have `class="clip"` so the engine manages its
  visibility lifecycle. Use `data-start` and `data-duration` (seconds).
- Animations: register a paused GSAP timeline on
  `window.__timelines["<composition-id>"]`. The engine seeks it on every
  `hf-seek` event. Do NOT use raw `requestAnimationFrame` loops.
- Audio: per-scene `<audio data-track-index="N" src="…"></audio>`. The
  engine handles the mux; do NOT add a post-render ffmpeg pass.
- Panels / cards: use a centered glass card with the scene title + the
  narration text. Stack title and body on a single track with a small
  (0.1-0.2s) start offset for stagger.
- Transitions: a `class="clip scene-transition"` div on its own track at
  the seam between scenes, fading white over 0.3s.

## TTS

Per-scene narration WAVs are pre-generated and live at:
  `output/scenes/scene_NNN_audio.wav`

Reference them with relative paths from the composition root, e.g.
`../scenes/scene_001_audio.wav` or absolute `file://` URLs. Each audio
file's length drives the corresponding scene's `data-duration`.

## Render command

After the composition is written, render it with:

```bash
npx --yes hyperframes render "{CONFIG.output_dir / 'hyperframes_project'}" \\
  -o "{output}" -f 30 -q high --crf 20 --resolution landscape --workers 2 --gpu
```

GPU is preferred (NVENC). If NVENC is unavailable, the engine falls back
to libx264 automatically.

## Skill reference

The HyperFrames skills are installed at `~/.agents/skills/`. Relevant
ones for this task:

- `hyperframes` — composition authoring contract
- `gsap` — paused-timeline + seek pattern
- `hyperframes-cli` — render/lint/inspect command reference
- `hyperframes-media` — TTS / asset preprocessing

## Output

Final video: `{output}`
"""
    return brief


def write_brief(brief_md: str, project_dir: Path) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    brief_path = project_dir / "BRIEF.md"
    brief_path.write_text(brief_md, encoding="utf-8")
    return brief_path


def invoke_agent(agent_bin: str, brief_path: Path, project_dir: Path) -> int:
    """Invoke the agent CLI in non-interactive mode with the brief."""
    if agent_bin == "claude":
        cmd = [
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            f"Read {brief_path} and follow the instructions to author a HyperFrames composition at {project_dir / 'index.html'}, then run the `Render command` section. Report only the final video path.",
        ]
    elif agent_bin == "codex":
        cmd = [
            "codex", "exec",
            "--full-auto",
            f"Read {brief_path} and follow the instructions to author a HyperFrames composition at {project_dir / 'index.html'}, then run the `Render command` section. Report only the final video path.",
        ]
    elif agent_bin == "gemini":
        cmd = [
            "gemini", "-p",
            f"Read {brief_path} and follow the instructions to author a HyperFrames composition at {project_dir / 'index.html'}, then run the `Render command` section. Report only the final video path.",
        ]
    else:
        # generic: print the brief to stdout and let the user paste it
        print(brief_path.read_text(encoding="utf-8"))
        return 0

    log.info("Invoking agent: %s", " ".join(cmd[:1]))
    proc = subprocess.run(cmd, cwd=str(project_dir.parent))
    return proc.returncode


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(prog="agent_render")
    p.add_argument("--input", required=True, help="Input PDF path")
    p.add_argument("--output", "-o", required=True, help="Output MP4 path")
    p.add_argument(
        "--intent",
        default="10-minute deep explanation",
        help="Render intent (e.g. '10-min deep explanation', '30-sec teaser')",
    )
    p.add_argument(
        "--target-minutes", type=int, default=10,
        help="Target video length in minutes",
    )
    p.add_argument(
        "--print-brief", action="store_true",
        help="Just print the brief path and exit; don't invoke the agent",
    )
    p.add_argument(
        "--agent",
        default=None,
        help="Agent binary to invoke (claude, codex, gemini, cursor, kilo). Auto-detected if omitted.",
    )
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    input_pdf = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not input_pdf.exists():
        log.error("Input PDF not found: %s", input_pdf)
        return 1

    project_dir = CONFIG.output_dir / "hyperframes_project"
    project_dir.mkdir(parents=True, exist_ok=True)

    brief = build_brief(
        input_pdf, args.intent, output, target_minutes=args.target_minutes
    )
    brief_path = write_brief(brief, project_dir)
    log.info("Wrote brief: %s", brief_path)

    if args.print_brief:
        print(brief_path)
        return 0

    agent = args.agent or _detect_agent()
    if not agent:
        log.error(
            "No agent CLI detected on PATH. Install one of: "
            "claude (Claude Code), codex, gemini, cursor, kilo. "
            "Or re-run with --print-brief to get the path to the brief."
        )
        return 2

    return invoke_agent(agent, brief_path, project_dir)


if __name__ == "__main__":
    sys.exit(main())
