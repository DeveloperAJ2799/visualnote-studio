import base64
import json
import os
import traceback
from pathlib import Path

import fitz
import httpx
import supabase
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sb_client = supabase.create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
)

KILO_BASE_URL = os.getenv("KILO_BASE_URL", "https://api.kilo.dev/v1")
KILO_API_KEY = os.getenv("KILO_API_KEY")
MIMO_TTS_BASE_URL = os.getenv("MIMO_TTS_BASE_URL", "https://api.xiaomimo.com/v1")
MIMO_TTS_API_KEY = os.getenv("MIMO_TTS_API_KEY")
NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/models/qwen/qwen2.5-vl-32b-instruct/generations"
NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY")


class GenerateManifestRequest(BaseModel):
    job_id: str
    pdf_url: str


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


def _update_progress(job_id: str, progress: int, status: str) -> None:
    sb_client.table("render_jobs").update({
        "progress": progress,
        "status": status,
    }).eq("id", job_id).execute()


def _upload_to_supabase_storage(
    local_path: Path, remote_path: str, content_type: str = "application/octet-stream"
) -> str:
    sb_client.storage.from_("assets").upload(
        remote_path, local_path.read_bytes(), {"content-type": content_type}
    )
    return f"{os.getenv('SUPABASE_URL')}/storage/v1/object/public/{remote_path}"


def _download_pdf(pdf_url: str, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.get(pdf_url, timeout=120.0) as resp:
        resp.raise_for_status()
        dest_path.write_bytes(resp.content)
    return dest_path


@app.post("/generate-manifest")
async def generate_manifest(req: GenerateManifestRequest):
    job_dir = Path(f"/tmp/jobs/{req.job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    local_pdf = job_dir / "input.pdf"

    try:
        _update_progress(req.job_id, 0, "processing_pipeline")

        # ================================================================
        # Stage 1 — PDF Ingestion (progress: 10)
        # Downloads PDF from pdf_url, extracts text per page via PyMuPDF,
        # packages into doc_content.json, uploads to Supabase Storage.
        # ================================================================
        _download_pdf(req.pdf_url, local_pdf)

        doc = fitz.open(local_pdf)
        pages_content = []
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            pages_content.append({"page": page_num, "text": text.strip()})
        doc.close()

        doc_content = {
            "document_title": local_pdf.stem,
            "source_url": req.pdf_url,
            "pages": pages_content,
        }

        doc_content_path = job_dir / "doc_content.json"
        doc_content_path.write_text(json.dumps(doc_content, ensure_ascii=False, indent=2))

        _upload_to_supabase_storage(
            doc_content_path,
            f"jobs/{req.job_id}/doc_content.json",
            "application/json",
        )
        _update_progress(req.job_id, 10, "processing_pipeline")

        # ================================================================
        # Stage 2 — LLM Council via Kilo Code (progress: 30)
        # Calls Kilo's OpenAI-compatible gateway with scene manifest schema.
        # Returns parsed scene_manifest with scenes array.
        # ================================================================
        raw_text = "\n\n".join(p["text"] for p in pages_content if p["text"])

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{KILO_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {KILO_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-3-5-sonnet",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a video script generation expert. "
                                "Generate a scene_manifest with a scenes array. "
                                "Each scene must have: scene_id (int), title (str), narration (str), "
                                "duration_s (float), frame_style (str: 'qwen_image'|'html_frame'|'title_card'), "
                                "highlights (list[str]), visual_props (dict)."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Generate a scene manifest for the following document content:\n\n{raw_text[:8000]}"
                            ),
                        },
                    ],
                    "temperature": 0.4,
                },
            )
            response.raise_for_status()
            llm_result = response.json()
            manifest_text = llm_result["choices"][0]["message"]["content"]

        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError:
            start = manifest_text.find("{")
            end = manifest_text.rfind("}")
            manifest = json.loads(manifest_text[start : end + 1])

        _update_progress(req.job_id, 30, "processing_pipeline")

        # ================================================================
        # Stage 3 — TTS Generation via MiMo TTS (progress: 60)
        # Iterates over scenes, calls MiMo TTS endpoint per scene narration,
        # saves MP3 locally, uploads to Supabase Storage.
        # Attaches audio_url to each scene object.
        # ================================================================
        scenes_dir = job_dir / "audio"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=120.0) as client:
            for scene in manifest.get("scenes", []):
                scene_id = scene.get("scene_id")
                narration = scene.get("narration", "")

                if not narration:
                    continue

                tts_response = await client.post(
                    f"{MIMO_TTS_BASE_URL}/chat/completions",
                    headers={
                        "api-key": MIMO_TTS_API_KEY or "",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "mimo-v2.5-tts",
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    "Read the following text in a warm, instructor-style voice. "
                                    f"Text: {narration}"
                                ),
                            },
                        ],
                        "audio": {"format": "mp3", "voice": "Chloe"},
                    },
                )
                tts_response.raise_for_status()
                tts_data = tts_response.json()

                audio_data = tts_data.get("choices", [{}])[0].get("message", {}).get("audio", {})
                if isinstance(audio_data, dict):
                    audio_b64 = audio_data.get("data") or audio_data.get("audio_base64")
                else:
                    audio_b64 = audio_data

                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    audio_path = scenes_dir / f"scene_{scene_id}.mp3"
                    audio_path.write_bytes(audio_bytes)

                    audio_url = _upload_to_supabase_storage(
                        audio_path,
                        f"jobs/{req.job_id}/audio/scene_{scene_id}.mp3",
                        "audio/mpeg",
                    )
                    scene["audio_url"] = audio_url

        _update_progress(req.job_id, 60, "processing_pipeline")

        # ================================================================
        # Stage 4 — NVIDIA NIM Fallback (progress: 90)
        # Only fires when frame_style == 'qwen_image'.
        # Generates static background image via Qwen2.5-VL, uploads to Supabase.
        # Attaches background_image_url to visual_props.
        # ================================================================
        if NIM_API_KEY:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for scene in manifest.get("scenes", []):
                    if scene.get("frame_style") == "qwen_image":
                        title = scene.get("title", "")
                        narration = scene.get("narration", "")[:200]

                        nim_response = await client.post(
                            NIM_ENDPOINT,
                            headers={
                                "Authorization": f"Bearer {NIM_API_KEY}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "prompt": (
                                    f"Educational biology illustration of {title}. "
                                    f"Key concept: {narration}. "
                                    "Scientific diagram, labeled parts, professional quality."
                                ),
                                "aspect_ratio": "16:9",
                                "image_format": "png",
                            },
                        )

                        if nim_response.status_code == 200:
                            nim_data = nim_response.json()
                            img_b64 = None
                            if "data" in nim_data and isinstance(nim_data["data"], list):
                                for item in nim_data["data"]:
                                    if "b64_json" in item:
                                        img_b64 = item["b64_json"]
                                        break

                            if img_b64:
                                img_path = job_dir / f"scene_{scene.get('scene_id')}_bg.png"
                                img_bytes = base64.b64decode(img_b64)
                                img_path.write_bytes(img_bytes)

                                img_url = _upload_to_supabase_storage(
                                    img_path,
                                    f"jobs/{req.job_id}/images/scene_{scene.get('scene_id')}_bg.png",
                                    "image/png",
                                )
                                if "visual_props" not in scene:
                                    scene["visual_props"] = {}
                                scene["visual_props"]["background_image_url"] = img_url

        _update_progress(req.job_id, 90, "processing_pipeline")

        # ================================================================
        # Final — Upload scene_manifest.json, mark manifest_ready
        # ================================================================
        manifest_path = job_dir / "scene_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

        manifest_url = _upload_to_supabase_storage(
            manifest_path,
            f"jobs/{req.job_id}/scene_manifest.json",
            "application/json",
        )

        sb_client.table("render_jobs").update({
            "progress": 100,
            "status": "manifest_ready",
            "manifest_url": manifest_url,
        }).eq("id", req.job_id).execute()

        return {"status": "ok", "manifest_url": manifest_url}

    except Exception as exc:
        tb = traceback.format_exc()
        print(tb)

        sb_client.table("render_jobs").update({
            "status": "failed",
            "error_message": str(exc)[:1000],
        }).eq("id", req.job_id).execute()

        raise HTTPException(status_code=500, detail=str(exc))