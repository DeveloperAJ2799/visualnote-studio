"""HTTP client for the MiMo V2.5 chat completions and TTS endpoints.

This module isolates all knowledge of MiMo's HTTP shape into one file. If the
real endpoint contract differs from the placeholders below, fix it here only.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class HTTPClient:
    """Calls MiMo V2.5 for LLM and TTS over HTTPS.

    All request/response shapes are isolated to this class so they can be fixed
    in one place after verifying the real MiMo API contract. Look for the
    `# TODO(MIMO):` markers below.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        tts_base_url: Optional[str] = None,
        tts_api_key: Optional[str] = None,
        tts_model: Optional[str] = None,
        timeout_s: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError(
                "HTTPClient requires a non-empty api_key. "
                "Set MIMO_API_KEY in .env or pass --mock to use the MockClient."
            )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.tts_base_url = (tts_base_url or base_url).rstrip("/")
        self.tts_api_key = tts_api_key or api_key
        self.tts_model = tts_model or "mimo-v2.5-tts"
        self.timeout_s = timeout_s
        self._sync = httpx.Client(timeout=timeout_s)

    def _headers(self) -> Dict[str, str]:
        # TODO(MIMO): confirm the auth header scheme. Common patterns are
        # "Authorization: Bearer <key>" or "X-API-Key: <key>".
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post_chat(self, system: str, user: str, *, json_mode: bool = True) -> str:
        # TODO(MIMO): confirm the chat completions path. Most providers use
        # "/chat/completions" with a body that mirrors OpenAI's.
        url = f"{self.base_url}/chat/completions"
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        logger.debug("POST %s model=%s", url, self.model)
        resp = self._sync.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        # TODO(MIMO): confirm the response shape. OpenAI-compatible responses
        # expose text at data["choices"][0]["message"]["content"].
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected MiMo chat response shape: {json.dumps(data)[:500]}"
            ) from exc

    def generate_scene_manifest(
        self, doc_text: str, doc_title_hint: str
    ) -> Dict[str, Any]:
        from ..prompts import SCENE_GEN_SYSTEM, scene_gen_user

        content = self._post_chat(SCENE_GEN_SYSTEM, scene_gen_user(doc_text, doc_title_hint))
        return _parse_json(content)

    def generate_manim_code(self, manim_prompt: str) -> str:
        from ..prompts import MANIM_GEN_SYSTEM, manim_gen_user

        content = self._post_chat(
            MANIM_GEN_SYSTEM, manim_gen_user(manim_prompt), json_mode=False
        )
        return _strip_code_fences(content)

    def generate_manim_retry(
        self, manim_prompt: str, prev_code: str, error: str
    ) -> str:
        from ..prompts import MANIM_GEN_SYSTEM, manim_retry_user

        content = self._post_chat(
            MANIM_GEN_SYSTEM,
            manim_retry_user(manim_prompt, prev_code, error),
            json_mode=False,
        )
        return _strip_code_fences(content)

    def generate_html_frame(
        self, scene_title: str, scene_narration: str, html_hint: str
    ) -> str:
        from ..prompts import HTML_GEN_SYSTEM, html_gen_user

        content = self._post_chat(
            HTML_GEN_SYSTEM,
            html_gen_user(scene_title, scene_narration, html_hint),
            json_mode=False,
        )
        return content.strip()

    def synthesize(self, text: str, voice: str = "instructor") -> bytes:
        # TODO(MIMO): confirm the TTS path. Many providers expose
        # "/audio/speech" with a body mirroring OpenAI's speech endpoint.
        url = f"{self.tts_base_url}/audio/speech"
        body: Dict[str, Any] = {
            "model": self.tts_model,
            "input": text,
            "voice": voice,
            "response_format": "wav",
        }
        logger.debug("POST %s model=%s voice=%s", url, self.tts_model, voice)
        resp = self._sync.post(url, headers=self._headers(), json=body)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "application/json" in ctype:
            # Some TTS endpoints return base64-encoded audio inside JSON.
            # TODO(MIMO): confirm whether this is the case for MiMo TTS.
            data = resp.json()
            for key in ("audio", "audio_base64", "data"):
                if key in data and isinstance(data[key], str):
                    return base64.b64decode(data[key])
            raise RuntimeError(
                f"Unexpected MiMo TTS JSON response: {json.dumps(data)[:500]}"
            )
        return resp.content


def _parse_json(content: str) -> Dict[str, Any]:
    """Parse JSON, tolerating stray markdown fences and surrounding prose."""
    text = _strip_code_fences(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise RuntimeError(f"Failed to parse MiMo JSON: {exc}\n--- payload ---\n{text[:1000]}")


def _strip_code_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()
