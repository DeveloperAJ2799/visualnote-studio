# VisualNote

Convert a study document (PDF, PPTX, DOCX) into a narrated explainer video
combining **Manim** math/diagram animations, **HTML frame** slides, and
**AI-synthesized narration** from the **Xiaomi MiMo V2.5** platform.

> Phase 1 (MVP) supports PDF input. PPTX and DOCX are scaffolded for Phase 2.

---

## Pipeline at a glance

```
PDF -> ingest -> MiMo V2.5 scene manifest -> [Manim | HTML | image | title]
                                                -> MiMo V2.5-TTS narration
                                                   -> FFmpeg NVENC assembly
                                                      -> final_explainer.mp4
```

See `pipeline/` for the module split, and PRD `v1.0` for the full spec.

---

## Quick start (mock mode, zero API spend)

```bash
# 1. install deps
pip install -r requirements.txt
playwright install chromium

# 2. run end-to-end with mocks (deterministic fake LLM + silent TTS)
python visualnote.py ^
  --input "Module 2 - The Fundamentals of Building Blocks of Life.pdf" ^
  --output output/final/explainer.mp4 ^
  --mock
```

The output MP4 lands at `output/final/explainer.mp4`. 1920x1080, 30 fps,
H.264 + AAC, with 0.3 s crossfades between scenes.

---

## Running with real MiMo V2.5

```bash
# 1. copy and fill in credentials
copy .env.example .env
# edit .env: set MIMO_API_KEY, MIMO_BASE_URL, MIMO_TTS_API_KEY, etc.

# 2. ensure MIMO_USE_MOCK is false (or omitted) in .env
# 3. run
python visualnote.py --input notes.pdf --output explainer.mp4
```

The HTTP client is isolated in `pipeline/clients/http_client.py`. All MiMo
endpoint/auth assumptions are marked `# TODO(MIMO):` for one-spot fixes after
verifying the real MiMo API contract.

---

## CLI flags

| Flag | Default | Purpose |
|---|---|---|
| `--input, -i` | required | Path to PDF/PPTX/DOCX |
| `--output, -o` | `output/final/explainer.mp4` | Final MP4 path |
| `--voice` | `instructor` | TTS voice preset |
| `--resolution` | `1080p` | `1080p` or `720p` |
| `--max-scenes` | unlimited | Cap scene count (smoke tests) |
| `--skip-manim` | false | Force all `manim_animation` scenes to title cards |
| `--mock` | false | Force `MockClient` regardless of env |
| `--dry-run` | false | Stop after producing `scene_manifest.json` |
| `--force-manifest` | false | Re-generate manifest even if cached |
| `--verbose, -v` | false | DEBUG-level logging |

---

## Output layout

```
output/
├── doc_content.json          # cached ingestion result
├── scene_manifest.json       # cached LLM manifest
├── assets/
│   ├── extracted/            # PDF images (12 for Module 2)
│   └── fetched/              # (Phase 2: Unsplash/Wikimedia)
├── scenes/
│   ├── scene_001.png         # per-scene visuals
│   ├── scene_002.mp4         # (mp4 for Manim, png otherwise)
│   ├── ...
│   └── scene_001_audio.wav   # per-scene TTS
├── frames/                   # HTML frame sources (for debugging)
└── final/
    └── explainer.mp4         # final output
```

Re-running the pipeline is **idempotent and resumable**: any scene whose
`scene_{id}.{mp4,png}` or `scene_{id}_audio.wav` already exists is skipped.

---

## Prerequisites

* **Python 3.10+** (tested on 3.12)
* **ffmpeg** with `h264_nvenc` (auto-detected; auto-falls back to `libx264`).
  The pipeline auto-uses the ffmpeg binary bundled with `imageio-ffmpeg` if no
  system ffmpeg is found.
* **Manim** (installed via `pip install -r requirements.txt`)
* **Playwright Chromium** (one-time: `playwright install chromium`)
* **MiMo V2.5** API key + base URL (only required for non-mock runs)

### Windows notes

* `pip install manim` works on Windows out of the box in Python 3.12.
* No Visual Studio Build Tools required for the dependencies in `requirements.txt`.
* If `playwright install chromium` errors on a corporate proxy, set
  `PLAYWRIGHT_DOWNLOAD_HOST` or run from a network with direct access.

### Manim install sanity check

```bash
manim --version
# Manim Community v0.18+ expected
```

### NVENC sanity check

```bash
ffmpeg -hide_banner -encoders | findstr h264_nvenc
```

If present, the assembler uses it. Otherwise it logs a warning and uses
`libx264` (still fast on RTX 4050 for the final encode).

---

## Architecture

* `config.py` — env-driven `Config` dataclass; auto-detects ffmpeg/manim.
* `pipeline/clients/base.py` — `MiMoClient` and `TTSClient` Protocols.
* `pipeline/clients/mock_client.py` — deterministic offline implementation
  (silent WAVs, fixed 4-scene manifest, sample Manim script, styled HTML).
* `pipeline/clients/http_client.py` — real MiMo API client. **All endpoint
  and auth assumptions are marked `# TODO(MIMO):` and isolated to this file.**
* `pipeline/prompts.py` — verbatim copies of the PRD §9 prompts + retry variant.
* `pipeline/ingestion.py` — pymupdf text + image extraction.
* `pipeline/script_gen.py` — manifest generation, validation, repair.
* `pipeline/manim_gen.py` — Manim code gen + subprocess render + retry loop.
* `pipeline/html_gen.py` — Playwright HTML frame render + Pillow fallback.
* `pipeline/image_fetcher.py` — PDF-asset lookup + blurred-bg composition.
* `pipeline/tts.py` — TTS synthesis + Coqui local fallback + silent fallback.
* `pipeline/assembler.py` — moviepy concat with crossfades + FFmpeg NVENC.
* `visualnote.py` — CLI orchestrator (this is what you run).

---

## Known limitations (Phase 1)

* **PPTX and DOCX** ingestion raise `NotImplementedError`. PDF only.
* **Unsplash and Wikimedia** image fetches are scaffolded but not implemented
  (PDF-asset-only for now).
* **Subtitle burn-in** is skipped (Phase 2 per PRD §12).
* **MiMo API endpoints** in `http_client.py` are placeholders marked
  `# TODO(MIMO):`. Verify with the real MiMo docs and patch in one place.
* **Manim intermediate write** is the slowest step (~3 min for 4 scenes at
  1080p). For larger projects, consider pre-rendering each scene to its own
  MP4 and using FFmpeg's `xfade` filter directly.

---

## Testing without a real PDF

```bash
# Use the included sample PDF, with 2 scenes only
python visualnote.py -i "Module 2 - The Fundamentals of Building Blocks of Life.pdf" --mock --max-scenes 2

# Stop right after the manifest to inspect it
python visualnote.py -i notes.pdf --mock --dry-run
```

The manifest is saved as `output/scene_manifest.json` and is human-readable.

---

## License

Personal project. Use at your own risk.
