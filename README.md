# VisualNote Studio

Convert any study document (PDF) into a **narrated explainer video** with animated diagrams, AI-generated visuals, and professional motion graphics.

## What it does

```
PDF → Ingest → LLM Scene Manifest → Visual Rendering → TTS Narration → HyperFrames Video
                                     ├── Manim animations
                                     ├── HTML frame slides
                                     ├── PDF image extraction
                                     └── AI image generation (Qwen/NVIDIA NIM)
```

**Output**: 1920x1080 MP4 with H.264 video + AAC audio, GSAP-animated panels, Ken Burns effects, and smooth transitions.

---

## Features

- **HyperFrames renderer** — HTML composition with class="clip" divs, paused GSAP timeline, per-scene audio tracks
- **GPU-accelerated encoding** — Auto-detects `h264_nvenc` for fast rendering
- **Multiple visual types**:
  - `manim_animation` — LLM-generated Manim scenes with retry logic
  - `html_frame` — Playwright-rendered HTML slides with Pillow fallback
  - `image_overlay` — PDF image extraction + keyword matching
  - `title_card` — Pillow-generated title cards
  - `qwen_image` — AI image generation via NVIDIA NIM API
- **Motion graphics** — Ken Burns background, panel slide-in, accent bar sweep, title clip-path reveal, staggered body text
- **Smooth transitions** — Colored radial gradient crossfades (no harsh white flashes)
- **Resumable pipeline** — Skips already-rendered scenes; re-run is idempotent

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Set up credentials
copy .env.example .env
# Edit .env with your API keys

# 3. Run the full pipeline
python run_deep_biology.py
```

### CLI flags

| Flag | Default | Purpose |
|---|---|---|
| `--pdf <path>` | first `*.pdf` in project root | Input PDF to convert |
| `--out <path>` | `output/final/<pdf_stem>_deep_explanation.mp4` | Output MP4 path |
| `--target-minutes <int>` | `10` | Target video length in minutes |
| `--voice <name>` | `Chloe` | TTS voice |
| `--skip-llm` | false | Reuse cached manifest; skip LLM generation |
| `--skip-tts` | false | Reuse cached audio files |
| `--skip-visuals` | false | Skip visual rendering; reuse existing images |
| `--force-visuals` | false | Re-render all visuals even if PNGs exist |

### Examples

```bash
# Auto-discover: pick up the first *.pdf in the project root
python run_deep_biology.py

# Convert a specific PDF
python run_deep_biology.py --pdf "Module 3 - Cells.pdf"

# Custom output path
python run_deep_biology.py --out "videos/my_lesson.mp4"

# Shorter video with a different voice
python run_deep_biology.py --target-minutes 5 --voice Aria

# Quick re-render (skip everything except the final video)
python run_deep_biology.py --skip-llm --skip-tts --skip-visuals

# Regenerate all visuals with AI
python run_deep_biology.py --skip-tts --force-visuals
```

---

## Providers

| Role | Provider | Env var |
|---|---|---|
| LLM (manifest + Manim + HTML) | Kilo Code AI Gateway | `KILO_API_KEY` |
| TTS (narration) | Xiaomi MiMo TTS | `MIMO_TTS_API_KEY` |
| Image generation | NVIDIA NIM (Qwen Image) | `NVIDIA_NIM_API_KEY` |

---

## Output layout

```
output/
├── doc_content.json          # Cached PDF ingestion
├── scene_manifest.json       # LLM-generated scene manifest
├── assets/
│   └── extracted/            # PDF images
├── scenes/
│   ├── scene_001.png         # Per-scene visuals
│   ├── scene_002.mp4         # (Manim output)
│   ├── scene_001_audio.wav   # Per-scene TTS
│   └── ...
├── hyperframes_project/      # Generated HTML composition
└── final/
    └── explainer.mp4         # Final output
```

---

## Architecture

- `run_deep_biology.py` — Main pipeline driver
- `hyperframes_render.py` — HTML composition builder with GSAP animations
- `deep_manifest.py` — LLM scene manifest generation
- `pipeline/visuals.py` — Visual orchestrator (routes to renderers)
- `pipeline/qwen_image.py` — NVIDIA NIM Qwen Image API client
- `pipeline/manim_gen.py` — Manim code generation + rendering
- `pipeline/html_gen.py` — Playwright HTML frame renderer
- `pipeline/image_fetcher.py` — PDF image extraction + composition
- `pipeline/tts.py` — TTS synthesis with caching
- `config.py` — Environment-driven configuration

---

## Requirements

- Python 3.10+ (tested on 3.12)
- Node.js (for HyperFrames CLI)
- FFmpeg with h264_nvenc (optional, for GPU encoding)
- Manim (for animation scenes)
- Playwright Chromium (`playwright install chromium`)

---

## License

MIT
