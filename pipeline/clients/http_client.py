"""HTTP client for the LLM (Kilo Code gateway) and TTS (Xiaomi MiMo) APIs.

This module isolates all knowledge of both APIs' HTTP shape in one file. The
two calls go to two completely different providers, so the class is split into
two independent client objects held together as one HTTPClient instance.

LLM (Kilo Code AI Gateway, OpenAI-compatible):
  - Endpoint: POST {KILO_BASE_URL}/chat/completions
  - Auth:     Authorization: Bearer <KILO_API_KEY>
  - Body:     {model, messages, temperature, response_format?}
  - Response: {choices: [{message: {content: "<text>"}}]}

TTS (Xiaomi MiMo Open Platform, chat-completions-based TTS):
  - Endpoint: POST {MIMO_TTS_BASE_URL}/chat/completions
  - Auth:     api-key: <MIMO_TTS_API_KEY>     (NOT Authorization: Bearer)
  - Body:     {model, messages, audio: {format: "wav", voice: "Chloe"}}
  - Response: {choices: [{message: {audio: {data: "<base64 PCM>"}}}]}
  - The audio bytes are raw 48kHz / 16-bit / mono PCM; we wrap with a WAV
    header before returning.
"""
from __future__ import annotations

import base64
import json
import logging
import struct
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# MiMo TTS returns 48 kHz, 16-bit, mono PCM.
MIMO_PCM_RATE = 48_000
MIMO_PCM_CHANNELS = 1
MIMO_PCM_SAMPLE_WIDTH = 2  # bytes per sample


def _wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate: int = MIMO_PCM_RATE) -> bytes:
    """Wrap raw PCM bytes with a standard RIFF/WAVE header."""
    n_channels = MIMO_PCM_CHANNELS
    sample_width = MIMO_PCM_SAMPLE_WIDTH
    byte_rate = sample_rate * n_channels * sample_width
    block_align = n_channels * sample_width
    data_size = len(pcm_bytes)
    riff_size = 36 + data_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,                       # fmt chunk size
        1,                        # PCM format
        n_channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
        b"data",
        data_size,
    )
    return header + pcm_bytes


class HTTPClient:
    """Calls Kilo (LLM) and MiMo (TTS) over HTTPS. All shapes are isolated here."""

    def __init__(
        self,
        kilo_base_url: str,
        kilo_api_key: str,
        kilo_model: str,
        tts_base_url: Optional[str] = None,
        tts_api_key: Optional[str] = None,
        tts_model: Optional[str] = None,
        timeout_s: float = 120.0,
    ) -> None:
        if not kilo_api_key:
            raise ValueError(
                "HTTPClient requires a non-empty kilo_api_key. "
                "Set KILO_API_KEY in .env or pass --mock to use the MockClient."
            )
        self.kilo_base_url = kilo_base_url.rstrip("/")
        self.kilo_api_key = kilo_api_key
        self.kilo_model = kilo_model
        self.tts_base_url = (tts_base_url or kilo_base_url).rstrip("/")
        self.tts_api_key = tts_api_key or kilo_api_key
        self.tts_model = tts_model or "mimo-v2.5-tts"
        self.timeout_s = timeout_s
        self._sync = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._sync.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _kilo_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.kilo_api_key}",
            "Content-Type": "application/json",
        }

    def _tts_headers(self) -> Dict[str, str]:
        return {
            "api-key": self.tts_api_key,
            "Content-Type": "application/json",
        }

    def _post_chat_kilo(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.4,
        timeout_s: Optional[float] = None,
    ) -> str:
        url = f"{self.kilo_base_url}/chat/completions"
        body: Dict[str, Any] = {
            "model": self.kilo_model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        logger.debug("POST %s model=%s", url, self.kilo_model)
        if timeout_s is not None and timeout_s != self.timeout_s:
            with httpx.Client(timeout=timeout_s) as tmp_client:
                resp = tmp_client.post(url, headers=self._kilo_headers(), json=body)
        else:
            resp = self._sync.post(url, headers=self._kilo_headers(), json=body)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Kilo chat call failed ({resp.status_code}): {resp.text[:1000]}"
            )
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected Kilo chat response shape: {json.dumps(data)[:500]}"
            ) from exc

    # ----- MiMoClient (LLM) Protocol methods -----

    def generate_scene_manifest(
        self, doc_text: str, doc_title_hint: str
    ) -> Dict[str, Any]:
        from ..prompts import SCENE_GEN_SYSTEM, scene_gen_user

        content = self._post_chat_kilo(
            [
                {"role": "system", "content": SCENE_GEN_SYSTEM},
                {"role": "user", "content": scene_gen_user(doc_text, doc_title_hint)},
            ],
            json_mode=True,
        )
        return _parse_json(content)

    def generate_manim_code(self, manim_prompt: str) -> str:
        from ..prompts import MANIM_GEN_SYSTEM, manim_gen_user

        content = self._post_chat_kilo(
            [
                {"role": "system", "content": MANIM_GEN_SYSTEM},
                {"role": "user", "content": manim_gen_user(manim_prompt)},
            ],
            json_mode=False,
        )
        return _strip_code_fences(content)

    def generate_manim_retry(
        self, manim_prompt: str, prev_code: str, error: str
    ) -> str:
        from ..prompts import MANIM_GEN_SYSTEM, manim_retry_user

        content = self._post_chat_kilo(
            [
                {"role": "system", "content": MANIM_GEN_SYSTEM},
                {"role": "user", "content": manim_retry_user(manim_prompt, prev_code, error)},
            ],
            json_mode=False,
        )
        return _strip_code_fences(content)

    def generate_html_frame(
        self, scene_title: str, scene_narration: str, html_hint: str
    ) -> str:
        from ..prompts import HTML_GEN_SYSTEM, html_gen_user

        content = self._post_chat_kilo(
            [
                {"role": "system", "content": HTML_GEN_SYSTEM},
                {"role": "user", "content": html_gen_user(scene_title, scene_narration, html_hint)},
            ],
            json_mode=False,
        )
        return content.strip()

    # ----- TTSClient Protocol methods -----

    def synthesize(self, text: str, voice: str = "Chloe") -> bytes:
        """Call MiMo TTS and return WAV bytes ready for moviepy.

        The MiMo response carries raw PCM 48kHz/16-bit/mono as base64 in
        `choices[0].message.audio.data`. We decode and wrap with a WAV header.
        """
        url = f"{self.tts_base_url}/chat/completions"
        body: Dict[str, Any] = {
            "model": self.tts_model,
            "messages": [
                # The user message is a short style cue; the assistant message
                # carries the actual text to be spoken.
                {
                    "role": "user",
                    "content": (
                        "Read the following text in a warm, instructor-style "
                        "voice at a calm, measured pace. Use a slightly "
                        "emphasized tone for technical terms."
                    ),
                },
                {"role": "assistant", "content": text},
            ],
            "audio": {
                "format": "wav",
                "voice": voice or "Chloe",
            },
            "stream": False,
        }
        logger.debug("POST %s model=%s voice=%s", url, self.tts_model, voice)
        resp = self._sync.post(url, headers=self._tts_headers(), json=body)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"MiMo TTS call failed ({resp.status_code}): {resp.text[:1000]}"
            )
        data = resp.json()
        audio = self._extract_audio(data)
        if audio is None:
            raise RuntimeError(
                "MiMo TTS response did not contain audio data. "
                f"Payload: {json.dumps(data)[:500]}"
            )
        pcm_bytes = base64.b64decode(audio)
        # If MiMo already returned a complete WAV (with 'RIFF' header), pass through.
        if pcm_bytes[:4] == b"RIFF":
            return pcm_bytes
        return _wrap_pcm_as_wav(pcm_bytes)

    @staticmethod
    def _extract_audio(data: Dict[str, Any]) -> Optional[str]:
        """Find the base64 audio string in a MiMo chat response."""
        try:
            choices = data.get("choices") or []
            if not choices:
                return None
            message = choices[0].get("message") or {}
            audio = message.get("audio")
            if isinstance(audio, dict):
                for key in ("data", "audio_base64", "audio_data"):
                    if key in audio and isinstance(audio[key], str):
                        return audio[key]
                if "url" in audio and isinstance(audio["url"], str):
                    # URL points to audio data; fetch it instead of base64-decoding
                    try:
                        url_resp = httpx.get(audio["url"], timeout=30)
                        url_resp.raise_for_status()
                        import base64 as _b64
                        return _b64.b64encode(url_resp.content).decode("ascii")
                    except Exception:
                        return None
            if isinstance(audio, str):
                return audio
        except (KeyError, IndexError, TypeError):
            return None
        return None


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
        raise RuntimeError(f"Failed to parse LLM JSON: {exc}\n--- payload ---\n{text[:1000]}")


def _strip_code_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()
