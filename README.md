# VisualNote Studio — Complete Project Documentation

## Architecture Overview

VisualNote Studio is a free-tier video generation SaaS prototype that converts PDF documents into narrated explainer videos using a serverless architecture.

### Tech Stack

| Layer | Technology | Deployment |
|-------|-----------|------------|
| Frontend | Next.js (App Router) | Vercel |
| Database & Storage | Supabase (Postgres, Auth, Storage) | Supabase Cloud |
| AI Pipeline (Backend) | Python FastAPI | Google Cloud Run (free tier: 2M req/month) |
| Video Rendering | Remotion Lambda (@remotion/lambda) | AWS Lambda (free tier) |
| LLM | Kilo Code Gateway (OpenAI-compatible) | Free tier credits |
| TTS | MiMo TTS (Xiaomi) | Free tier |
| Image Generation | NVIDIA NIM Qwen2.5-VL (fallback only) | 1000 free calls |

### Data Flow

```
User uploads PDF
       ↓
Next.js → creates render_jobs row (status: queued)
       ↓
Next.js → POST to FastAPI /generate-manifest
       ↓
FastAPI (Stage 1): PDF text extracted → doc_content.json → Supabase Storage
FastAPI (Stage 2): Kilo Code LLM → scene_manifest.json with scenes
FastAPI (Stage 3): MiMo TTS → MP3 audio per scene → Supabase Storage
FastAPI (Stage 4): NVIDIA NIM (if frame_style='qwen_image') → images → Supabase Storage
       ↓
FastAPI → status: manifest_ready, manifest_url populated
       ↓
Next.js → POST to /api/render → renderMediaOnLambda()
       ↓
Remotion Lambda reads manifest → renders MP4 → uploads to S3
       ↓
Polling loop → status: complete, video_url populated
       ↓
User sees video player in browser
```

---

## Project Structure

```
visualnote-studio/
├── apps/
│   ├── web/                          # Next.js App Router frontend
│   │   ├── src/
│   │   │   ├── lib/
│   │   │   │   └── supabase.ts       # Supabase client initialization
│   │   │   └── app/
│   │   │       ├── actions.ts        # Server action (createRenderJob)
│   │   │       ├── page.tsx          # Main page
│   │   │       ├── components/
│   │   │       │   └── VideoGenerator.tsx  # Main UI component
│   │   │       └── api/
│   │   │           └── render/
│   │   │               └── route.ts   # API route → triggers Remotion Lambda
│   │   └── package.json
│   └── remotion/                     # Remotion project (video rendering)
│       ├── src/
│       │   ├── VideoComposition.tsx  # Main composition (manifest reader + scene router)
│       │   └── scenes/
│       │       ├── TitleCard.tsx      # Intro/section break scenes
│       │       ├── SplitComparison.tsx # Pros/Cons, Versus, Before/After
│       │       ├── ListCascade.tsx    # Chronological steps, bullet takeaways
│       │       ├── DataCallout.tsx    # Stat callouts, key percentages
│       │       ├── MediaFocus.tsx     # Images from NVIDIA NIM (Ken Burns zoom)
│       │       └── ConceptMap.tsx     # Relational diagrams (SVG hub-and-spoke)
│       └── scripts/
│           └── render.ts              # Script to trigger Lambda render locally
├── services/
│   └── pipeline/                     # Python FastAPI service (Cloud Run)
│       ├── main.py                   # 4-stage pipeline endpoint
│       ├── requirements.txt
│       └── Dockerfile
├── pipeline/                         # Existing Python pipeline (root-level)
│   ├── ingestion.py                  # PDF text extraction (PyMuPDF)
│   ├── script_gen.py                 # Manifest generation
│   ├── tts.py                        # TTS synthesis (MiMo)
│   ├── qwen_image.py                 # NVIDIA NIM image generation
│   ├── assembler.py                  # Moviepy video assembly
│   ├── clients/
│   │   ├── http_client.py           # Kilo + MiMo HTTP client
│   │   ├── base.py                   # Protocol definitions
│   │   └── mock_client.py            # Mock for testing
│   └── council/                      # Multi-agent LLM deliberation
│       ├── orchestrator.py
│       ├── llm.py                    # Retry + fallback logic
│       ├── council_config.json       # Free-tier model config
│       └── ...
├── supabase/
│   └── render_jobs.sql              # SQL to create render_jobs table
├── config.py                        # Centralized config + env vars
├── visualnote.py                    # CLI orchestrator for existing pipeline
└── requirements.txt                 # Unified Python dependencies
```

---

## All Files Created or Modified by AI Assistant

### 1. `/apps/web/src/lib/supabase.ts`
Supabase client initialization using `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

### 2. `/apps/web/src/app/actions.ts`
Server action that:
- Inserts a new `render_jobs` row with `pdf_url` and `status: queued`
- POSTs to FastAPI `PIPELINE_CLOUD_RUN_URL` with `job_id` and `pdf_url`
- Returns the new `job_id`

### 3. `/apps/web/src/app/page.tsx`
Simple page that renders the `VideoGenerator` component.

### 4. `/apps/web/src/app/components/VideoGenerator.tsx`
Main UI component featuring:
- "Generate Video" button → calls `createRenderJob` server action
- **STATUS_MAP** — maps backend statuses to customer-facing labels:
  - `queued` → "Uploading your PDF..." (0%)
  - `processing_pipeline` → "Processing your content..." (reads live `progress` column 10-90%)
  - `manifest_ready` → "Preparing video render engine..." (90%)
  - `rendering_video` → "Rendering your video frames with Remotion..." (95%)
  - `complete` → "Your video is ready!" (100%)
  - `failed` → displays `error_message` in red alert container
- Smooth progress bar with CSS `transition: width 0.3s ease-out`
- Supabase Realtime subscription on both `status` AND `progress` columns
- HTML5 `<video>` player when `video_url` is populated

### 5. `/apps/web/src/app/api/render/route.ts`
API route that:
- Validates `job_id` and `manifest_url` from request body
- Sets `status = rendering_video` in Supabase
- Calls `renderMediaOnLambda()` with `VideoComposition` composition and `manifest_url` as input prop
- Returns immediately with `{ render_id, bucket }`
- Uses `setTimeout(0)` to schedule background polling without blocking the response
- `pollRenderProgress()` calls `getRenderProgress()` every 5 seconds
- On `completed`: extracts S3 URL → updates `video_url` + `status: complete`
- On `failed`: updates `status: failed` + `error_message`

### 6. `/apps/remotion/src/VideoComposition.tsx`
Main Remotion composition:
- Fetches `scene_manifest.json` from `manifest_url`
- Maps `frame_style` string → scene component:
  - `title_card` → `TitleCard`
  - `split_comparison` → `SplitComparison`
  - `list_cascade` → `ListCascade`
  - `data_callout` → `DataCallout`
  - `qwen_image` → `MediaFocus`
  - `concept_map` → `ConceptMap`
- Renders each scene inside a `<Sequence>` with duration from `audio_duration_s * 30` fps
- Each scene component receives `audio_url` → renders `<Audio src={audio_url} />`

### 7. `/apps/remotion/src/scenes/TitleCard.tsx`
- **Design**: Dark background `#0F0F1A`, spring slide-up animation, thin indigo accent sweep
- **Props**: `title`, `visual_props.primary_text`, `audio_url`, `durationInFrames`

### 8. `/apps/remotion/src/scenes/SplitComparison.tsx`
- **Design**: Vertically split screen, left/right contrasting tones, dual spring inward from edges
- **Props**: `visual_props.primary_text`, `visual_props.secondary_text`, `visual_props.items`

### 9. `/apps/remotion/src/scenes/ListCascade.tsx`
- **Design**: Items slide in sequentially from left with 15-frame offset per item, vertical connector line
- **Props**: `title`, `visual_props.items`

### 10. `/apps/remotion/src/scenes/DataCallout.tsx`
- **Design**: Large typography with spring overshoot scale, slow fade-in label underneath
- **Props**: `visual_props.metric`, `visual_props.primary_text`

### 11. `/apps/remotion/src/scenes/MediaFocus.tsx`
- **Design**: Ken Burns zoom effect (`interpolate(frame, [0, durationInFrames], [1, 1.15])`), text card overlay
- **Props**: `scene_id`, `visual_props.primary_text`, `visual_props.image_url`

### 12. `/apps/remotion/src/scenes/ConceptMap.tsx`
- **Design**: SVG hub-and-spoke, center node pops first, connecting lines draw themselves via `strokeDashoffset`
- **Props**: `visual_props.primary_text`, `visual_props.items`

### 13. `/apps/remotion/scripts/render.ts`
Local script to trigger a Remotion Lambda render using `renderMediaOnLambda()`.

### 14. `/services/pipeline/main.py`
FastAPI app with `POST /generate-manifest` endpoint:
- **Stage 1 (progress: 10)**: Downloads PDF, extracts text via PyMuPDF, saves `doc_content.json` → Supabase Storage
- **Stage 2 (progress: 30)**: Calls Kilo Code LLM (`https://api.kilo.dev/v1`, model `claude-3-5-sonnet`) to generate structured scene manifest
- **Stage 3 (progress: 60)**: Per-scene MiMo TTS synthesis, MP3 saved and uploaded, `audio_url` added to scene
- **Stage 4 (progress: 90)**: NVIDIA NIM Qwen2.5-VL only when `frame_style == 'qwen_image'`, background image uploaded, added to `visual_props.background_image_url`
- **Final**: Uploads `scene_manifest.json`, sets `status: manifest_ready`
- **Error handling**: `try/except` → `status: failed`, `error_message` saved

### 15. `/services/pipeline/Dockerfile`
Python 3.11 slim image, installs requirements, runs uvicorn on port 8080.

### 16. `/supabase/render_jobs.sql`
```sql
CREATE TYPE render_job_status AS ENUM (
  'queued', 'processing_pipeline', 'manifest_ready',
  'rendering_video', 'complete', 'failed'
);

CREATE TABLE render_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  user_id UUID,
  pdf_url TEXT,
  manifest_url TEXT,
  video_url TEXT,
  status render_job_status DEFAULT 'queued',
  progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  error_message TEXT
);

ALTER TABLE render_jobs ENABLE ROW LEVEL SECURITY;
```

### 17. `/requirements.txt` (unified)
Consolidated Python dependencies. Note: `manim` is commented out — requires system Cairo/GObject libs.

### 18. `/config.py` (modified)
Changed LLM defaults to free-tier models:
- `kilo_model`: `kilo-auto/free` (was `anthropic/claude-sonnet-4.5`)
- `kilo_fallback_model`: `stepfun/step-3.7-flash:free` (was `anthropic/claude-sonnet-4`)

---

## Environment Variables Required

### Next.js / Frontend
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
PIPELINE_CLOUD_RUN_URL=https://your-pipeline-service.run.app
REMOTION_SERVE_URL=https://your-remotion.vercel.app
REMOTION_APP_FUNCTION_NAME=remotion-app-prod-...
REMOTION_AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

### Python Pipeline (Cloud Run)
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
KILO_API_KEY=your-kilo-api-key
MIMO_TTS_API_KEY=your-mimo-api-key
NVIDIA_NIM_API_KEY=your-nvidia-nim-api-key
```

---

## Free-Tier Constraints

| Service | Limit | Strategy |
|---------|-------|----------|
| Kilo Code | Finite free credits | Use `kilo-auto/free` model, add retry logic |
| MiMo TTS | Free with no billing | Swap from ElevenLabs, rewrite TTS payload shape |
| NVIDIA NIM | 1000 calls free | Only fire when `frame_style == 'qwen_image'`, use Remotion React as primary visuals |
| GCP Cloud Run | 2M req/month free | FastAPI containerized here |
| Supabase | 500MB DB, 1GB storage | Store manifest + assets only |
| AWS Lambda (Remotion) | Free tier | 1M free requests, 400K GB-seconds |

**Smart strategy**: NVIDIA NIM is the fallback only. Primary visuals = Remotion React components (unlimited free renders).

---

## Active Errors and Issues in the Codebase

### ERROR 1: `import '@remotion/react'` in Next.js API route (`apps/web/src/app/api/render/route.ts`)
- **Severity**: Critical — breaks build
- **Location**: `apps/web/src/app/api/render/route.ts` imports `renderMediaOnLambda` and `getRenderProgress` from `@remotion/lambda`
- **Issue**: `@remotion/lambda` is a Node.js-only package. It cannot be used in a Next.js API route (Vercel serverless functions) without proper external configuration. The package relies on AWS SDK which may have compatibility issues in serverless environments.
- **Fix needed**: Move Remotion Lambda triggering to a separate Node.js microservice or use `@remotion/lambda`'s deployed endpoint directly via HTTP fetch instead of importing the package in Next.js.

### ERROR 2: Missing `next.config.js` / TypeScript config in `/apps/web/`
- **Severity**: High — Next.js project won't build without config files
- **Location**: `apps/web/` directory has `package.json` but no `next.config.js`, `tsconfig.json`, or `next-env.d.ts`
- **Fix needed**: Run `npx create-next-app apps/web --typescript --app --src-dir` to regenerate proper config, or manually create:
  - `next.config.js` (or `.mjs`)
  - `tsconfig.json`
  - `src/app/layout.tsx` (required for App Router)

### ERROR 3: `services/pipeline/requirements.txt` still exists after consolidation
- **Severity**: Low — maintenance issue
- **Location**: `services/pipeline/requirements.txt` and `requirements.txt` both exist
- **Fix needed**: Delete `services/pipeline/requirements.txt` (unified root `requirements.txt` already has all deps)

### ERROR 4: `import fitz` inside function body in `services/pipeline/main.py`
- **Severity**: Medium — import statement inside function body at line 61 and 166
- **Location**: `services/pipeline/main.py` lines 61, 166
- **Issue**: `import fitz` and `import base64` are called inside the `generate_manifest_endpoint` function. While this works, it is non-idiomatic and slows down repeated calls. `base64` is a stdlib module, no install needed.
- **Fix needed**: Move imports to top of file. Also `fitz` (PyMuPDF) should be in `requirements.txt` — it was included in the unified `requirements.txt`.

### ERROR 5: `from pathlib import Path as P` alias unused in `services/pipeline/main.py`
- **Severity**: Low — dead code
- **Location**: `services/pipeline/main.py` line 220
- **Issue**: `from pathlib import Path as P` is imported but `P` is never used (local `img_path` uses `job_dir` directly)
- **Fix needed**: Remove the unused `P` import alias

### ERROR 6: `REMOTION_APP_FUNCTION_NAME` vs `REMOTION_FUNCTION_NAME` environment variable mismatch
- **Severity**: Medium — runtime error likely
- **Location**: `apps/web/src/app/api/render/route.ts` uses `REMOTION_APP_FUNCTION_NAME`; `apps/remotion/scripts/render.ts` uses `REMOTION_FUNCTION_NAME`
- **Issue**: The Remotion render script uses `process.env.REMOTION_FUNCTION_NAME` while the API route uses `process.env.REMOTION_APP_FUNCTION_NAME`. These must be consistent.
- **Fix needed**: Use a consistent env var name across all files. Recommended: `REMOTION_APP_FUNCTION_NAME` throughout.

### ERROR 7: `nvim` (Neovim) process running and using significant CPU
- **Severity**: Low — infrastructure noise
- **Note**: This is not a code error but an active process on the system using CPU.

### ERROR 8: Remotion scene components may have missing props at runtime
- **Severity**: Medium — runtime error risk
- **Location**: Multiple scene files in `apps/remotion/src/scenes/`
- **Issue**: Scene components receive `visual_props` as `Record<string, any>` but some components (like `MediaFocus`) expect specific string fields. If `image_url` is missing or `visual_props` is `undefined`, the component will crash.
- **Fix needed**: Add defensive defaults and null checks in each scene component.

### ERROR 9: No `layout.tsx` in Next.js App Router project
- **Severity**: High — Next.js App Router requires `app/layout.tsx`
- **Location**: `apps/web/src/app/`
- **Issue**: `page.tsx` exists but no `layout.tsx`. Next.js App Router requires this file for proper app structure.
- **Fix needed**: Create `apps/web/src/app/layout.tsx` with root layout.

### ERROR 10: `services/pipeline/main.py` has hardcoded Kilo base URL
- **Severity**: Low — flexibility
- **Location**: `services/pipeline/main.py` line 19
- **Issue**: `KILO_BASE_URL = "https://api.kilo.dev/v1"` is hardcoded instead of reading from environment variable. The existing `config.py` uses `https://api.kilo.ai/api/gateway` as default.
- **Fix needed**: Use `os.getenv("KILO_BASE_URL", "https://api.kilo.dev/v1")` for consistency with the rest of the codebase, or make it configurable.

### ERROR 11: Missing `MIMO_TTS_API_KEY` in `.env.example`
- **Severity**: Medium — TTS won't work without it
- **Location**: `.env.example` line 30
- **Issue**: `MIMO_TTS_API_KEY=` is present but empty and the key must be provided. Also the `MIMO_TTS_BASE_URL` uses `api.xiaomimimo.com/v1` which may differ from what the existing pipeline expects.
- **Fix needed**: Ensure user provides a valid MiMo TTS API key and verifies the endpoint URL.

### ERROR 12: Supabase `storage.from_("assets")` bucket assumption
- **Severity**: Medium — runtime error
- **Location**: `services/pipeline/main.py` line 37
- **Issue**: Code assumes a storage bucket named `"assets"` exists in Supabase. If the bucket doesn't exist or the service role key lacks permission, this will fail at runtime.
- **Fix needed**: Either create the `assets` bucket in Supabase or use an existing bucket name. Also consider using `sb_client.storage.from_("assets").get_public_url()` instead of constructing the URL manually.

### ERROR 13: Remotion render script uses wrong env var `AWS_REGION` instead of `REMOTION_AWS_REGION`
- **Severity**: Medium — render script will fail
- **Location**: `apps/remotion/scripts/render.ts` line 7
- **Issue**: Uses `process.env.AWS_REGION` but the API route uses `process.env.REMOTION_AWS_REGION`. Inconsistent.
- **Fix needed**: Use `REMOTION_AWS_REGION` consistently.

### ERROR 14: No error boundary in Next.js VideoGenerator component
- **Severity**: Low — unhandled promise rejection
- **Location**: `apps/web/src/app/components/VideoGenerator.tsx`
- **Issue**: If `createRenderJob()` throws, the error propagates without user feedback (no error UI shown to user).
- **Fix needed**: Wrap `createRenderJob()` call in try/catch within `handleGenerate()`.

### ERROR 15: `services/pipeline/main.py` imports are non-ideal for production
- **Severity**: Low — code quality
- **Location**: `services/pipeline/main.py`
- **Issue**: Multiple imports like `import fitz`, `import base64` are done inside the function body (lines 61, 166) which makes cold starts slower. The `supabase` package is imported at module level (good).
- **Fix needed**: Move all imports to top of file for faster cold starts on Cloud Run.

### ERROR 16: Missing `app/layout.tsx` → Next.js build will fail
- **Severity**: High — build-blocking
- **See ERROR 9**.

### ERROR 17: `services/pipeline/main.py` line 19 — inconsistent Kilo URL
- **Severity**: Low — see ERROR 10.

### ERROR 18: `apps/remotion/src/VideoComposition.tsx` uses `index` parameter but never reads it
- **Severity**: Low — dead variable
- **Location**: `apps/remotion/src/VideoComposition.tsx` line 45 (`const renderScene = (scene: Scene, index: number)`)
- **Fix needed**: Remove `index` parameter since it's not used inside the function.

---

## Deployment Checklist

### Supabase
1. Create project at supabase.com
2. Run `supabase/render_jobs.sql` in SQL editor
3. Create `assets` storage bucket (public)
4. Copy `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### Google Cloud Run (Pipeline)
1. `cd services/pipeline`
2. `docker build -t pipeline .`
3. `gcloud run deploy pipeline --region=us-central1 --allow-unauthenticated`
4. Copy URL as `PIPELINE_CLOUD_RUN_URL`

### Vercel (Frontend)
1. `cd apps/web`
2. `vercel deploy`
3. Set env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `PIPELINE_CLOUD_RUN_URL`, `REMOTION_SERVE_URL`, `REMOTION_APP_FUNCTION_NAME`, `REMOTION_AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

### Remotion Deployment
1. `cd apps/remotion`
2. `npx remotion lambda deploy`
3. Copy the deployed serve URL as `REMOTION_SERVE_URL`
4. Copy the function name as `REMOTION_APP_FUNCTION_NAME`

### AWS Lambda (Remotion)
1. Follow Remotion Lambda deployment guide
2. Ensure IAM role has permissions for S3 and CloudWatch
3. Copy `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `REMOTION_AWS_REGION`, `REMOTION_APP_FUNCTION_NAME` to Vercel env vars