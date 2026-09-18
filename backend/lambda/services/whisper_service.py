"""
Ledgerly - Whisper Fallback Service for 23 Indian Languages
Covers AWS Transcribe gaps: Assamese (as), Sanskrit (sa), Sindhi (sd), Urdu (ur),
plus Odia fine-tune and gap langs via nearest fallback.

Provider options (env WHISPER_PROVIDER):
- huggingface : POST https://api-inference.huggingface.co/models/{model} with HF token
- openai      : POST https://api.openai.com/v1/audio/transcriptions (Whisper API)
- selfhosted  : POST {WHISPER_ENDPOINT_URL}/transcribe (custom faster-whisper)
If no provider configured, service reports not configured and caller falls back to AWS nearest.
"""

import os
import json
import base64
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Tuple


class WhisperError(Exception):
    pass

class WhisperUnavailableError(WhisperError):
    pass

class WhisperTranscriptionFailedError(WhisperError):
    pass


# Map ledger language_code → whisper language param
# Whisper uses ISO 639-1: as, bn, gu, hi, kn, ml, mr, ne, pa, sa, sd, ta, te, ur, en
WHISPER_LANG_MAP = {
    "as": "as", "as-IN": "as",
    "bn": "bn", "bn-IN": "bn",
    "gu": "gu", "gu-IN": "gu",
    "hi": "hi", "hi-IN": "hi",
    "kn": "kn", "kn-IN": "kn",
    "ml": "ml", "ml-IN": "ml",
    "mr": "mr", "mr-IN": "mr",
    "ne": "ne", "ne-NP": "ne", "ne-IN": "ne",
    "or": "or", "or-IN": "or",
    "pa": "pa", "pa-IN": "pa",
    "sa": "sa", "sa-IN": "sa",
    "sd": "sd", "sd-IN": "sd",
    "ta": "ta", "ta-IN": "ta",
    "te": "te", "te-IN": "te",
    "ur": "ur", "ur-IN": "ur",
    "en": "en", "en-IN": "en", "en-US": "en",
    "auto": "auto",
}

# Models per language (HF)
HF_MODEL_MAP = {
    "as": "openai/whisper-large-v3",
    "sa": "openai/whisper-large-v3",
    "sd": "openai/whisper-large-v3",
    "ur": "openai/whisper-large-v3",
    "or": "vasista22/whisper-or-large-v2",  # Odia fine-tune if available
    "default": "openai/whisper-large-v3",
}


class WhisperService:
    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        hf_token: Optional[str] = None,
        openai_key: Optional[str] = None,
        provider: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self.endpoint_url = endpoint_url or os.environ.get("WHISPER_ENDPOINT_URL", "")
        self.hf_token = hf_token or os.environ.get("HF_TOKEN", os.environ.get("HUGGINGFACE_TOKEN", ""))
        self.openai_key = openai_key or os.environ.get("OPENAI_API_KEY", "")
        self.provider = (provider or os.environ.get("WHISPER_PROVIDER", "")).lower().strip()
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        # Auto-detect provider if not explicit but endpoint/token present
        if not self.provider:
            if self.endpoint_url and "huggingface.co" in self.endpoint_url:
                self.provider = "huggingface"
            elif self.openai_key:
                self.provider = "openai"
            elif self.endpoint_url:
                self.provider = "selfhosted"

    def is_configured(self) -> bool:
        # Configured if any provider creds present
        if self.provider == "huggingface" and self.hf_token:
            return True
        if self.provider == "openai" and self.openai_key:
            return True
        if self.provider == "selfhosted" and self.endpoint_url:
            return True
        # Also allow endpoint_url alone as generic selfhosted
        if self.endpoint_url:
            return True
        return False

    def _map_lang(self, lang: Optional[str]) -> str:
        if not lang:
            return "auto"
        key = str(lang).strip()
        if key in WHISPER_LANG_MAP:
            return WHISPER_LANG_MAP[key]
        lower = key.lower()
        if lower in WHISPER_LANG_MAP:
            return WHISPER_LANG_MAP[lower]
        # Short code
        if len(key) == 2:
            return key.lower()
        return key.lower()

    def _transcribe_huggingface(self, audio_bytes: bytes, language: str, media_format: str = "ogg") -> Tuple[str, str]:
        model = HF_MODEL_MAP.get(language, HF_MODEL_MAP["default"])
        # HF inference for whisper-large-v3 often uses pipeline with language param via query
        # Use generic endpoint: https://api-inference.huggingface.co/models/{model}
        url = f"https://api-inference.huggingface.co/models/{model}"
        # HF Whisper expects raw audio bytes with content-type audio/*
        req = urllib.request.Request(url, data=audio_bytes, method="POST")
        req.add_header("Authorization", f"Bearer {self.hf_token}")
        # Try to set content-type based on format
        ctype = "audio/ogg" if media_format == "ogg" else f"audio/{media_format}"
        req.add_header("Content-Type", ctype)
        # Some HF models accept language via header? Use query param if needed
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # HF returns {"text": "..."} or [{"text": "..."}]
            if isinstance(data, dict) and "text" in data:
                text = str(data["text"]).strip()
                if not text:
                    raise WhisperTranscriptionFailedError("Whisper returned empty transcript")
                return text, language if language != "auto" else "auto"
            if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0]:
                text = str(data[0]["text"]).strip()
                if not text:
                    raise WhisperTranscriptionFailedError("Whisper returned empty transcript")
                return text, language if language != "auto" else "auto"
            # Error shape: {"error": "..."}
            if isinstance(data, dict) and "error" in data:
                raise WhisperUnavailableError(f"HuggingFace error: {data['error']}")
            raise WhisperTranscriptionFailedError(f"Unexpected HF response: {data}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            if e.code in (401, 403):
                raise WhisperUnavailableError(f"HF auth failed [{e.code}]: {body}")
            raise WhisperUnavailableError(f"HF Whisper failed [{e.code}]: {body}")
        except urllib.error.URLError as e:
            raise WhisperUnavailableError(f"HF connection failed: {str(e)}")

    def _transcribe_openai(self, audio_bytes: bytes, language: str, media_format: str = "ogg") -> Tuple[str, str]:
        # OpenAI /v1/audio/transcriptions expects multipart/form-data
        # Use manual boundary
        import mimetypes, uuid
        boundary = f"----LedgerlyBoundary{uuid.uuid4().hex}"
        filename = f"audio.{media_format}"
        # Build multipart body
        body_parts = []
        # model field
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body_parts.append(b"whisper-1\r\n")
        # language field if not auto
        if language and language != "auto":
            body_parts.append(f"--{boundary}\r\n".encode())
            body_parts.append(b'Content-Disposition: form-data; name="language"\r\n\r\n')
            body_parts.append(f"{language}\r\n".encode())
        # file field
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
        ctype = mimetypes.guess_type(filename)[0] or "audio/ogg"
        body_parts.append(f"Content-Type: {ctype}\r\n\r\n".encode())
        body_parts.append(audio_bytes)
        body_parts.append(b"\r\n")
        body_parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(body_parts)

        url = "https://api.openai.com/v1/audio/transcriptions"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {self.openai_key}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = str(data.get("text", "")).strip()
            if not text:
                raise WhisperTranscriptionFailedError("OpenAI Whisper returned empty transcript")
            # OpenAI may return language if auto
            detected = data.get("language", language)
            return text, detected
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise WhisperUnavailableError(f"OpenAI Whisper failed [{e.code}]: {body}")
        except urllib.error.URLError as e:
            raise WhisperUnavailableError(f"OpenAI connection failed: {str(e)}")

    def _transcribe_selfhosted(self, audio_bytes: bytes, language: str, media_format: str = "ogg") -> Tuple[str, str]:
        # Expects POST {endpoint}/transcribe with JSON {audio_base64, language, media_format}
        # Or raw bytes POST
        url = self.endpoint_url.rstrip("/")
        # Try JSON base64 first (compatible with Ledgerly's own transcribe endpoint shape)
        payload = json.dumps({
            "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            "language": language,
            "media_format": media_format,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.hf_token:
            req.add_header("Authorization", f"Bearer {self.hf_token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # Expect {"text": "...", "language": "..."} or {"transcript": "..."}
            text = str(data.get("text") or data.get("transcript") or data.get("result") or "").strip()
            if not text:
                # Try if response is {"success": true, "transcript": "..."}
                text = str(data.get("transcript", "")).strip()
            if not text:
                raise WhisperTranscriptionFailedError(f"Selfhosted returned empty: {data}")
            detected = str(data.get("language") or data.get("detected_language") or language)
            return text, detected
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise WhisperUnavailableError(f"Selfhosted Whisper failed [{e.code}]: {body}")
        except urllib.error.URLError as e:
            raise WhisperUnavailableError(f"Selfhosted connection failed: {str(e)}")

    def transcribe_audio_bytes(self, audio_bytes: bytes, language_code: Optional[str] = None, media_format: str = "ogg") -> Tuple[str, str]:
        if not audio_bytes:
            raise WhisperTranscriptionFailedError("Audio bytes empty")
        lang = self._map_lang(language_code)
        if not self.is_configured():
            raise WhisperUnavailableError("Whisper not configured (set WHISPER_ENDPOINT_URL or HF_TOKEN or OPENAI_API_KEY).")
        if self.provider == "huggingface":
            return self._transcribe_huggingface(audio_bytes, lang, media_format)
        if self.provider == "openai":
            return self._transcribe_openai(audio_bytes, lang, media_format)
        # Default selfhosted
        return self._transcribe_selfhosted(audio_bytes, lang, media_format)

    def transcribe_s3_uri(self, s3_uri: str, language_code: Optional[str] = None, media_format: str = "ogg", timeout_seconds: int = 30) -> Tuple[str, str]:
        # For S3 we need to fetch bytes via S3 then delegate to audio_bytes
        # Reuse boto3 S3 fetch if available
        try:
            import boto3
            if s3_uri.startswith("s3://"):
                path = s3_uri[5:]
                bucket, key = path.split("/", 1)
                s3 = boto3.client("s3", region_name=self.region_name)
                obj = s3.get_object(Bucket=bucket, Key=key)
                audio_bytes = obj["Body"].read()
                return self.transcribe_audio_bytes(audio_bytes, language_code=language_code, media_format=media_format)
        except Exception as e:
            raise WhisperUnavailableError(f"Failed to fetch S3 for Whisper: {str(e)}")
        raise WhisperUnavailableError("Invalid S3 URI for Whisper")
