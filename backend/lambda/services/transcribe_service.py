"""
Ledgerly - AWS Transcribe Speech-to-Text Service (Multilingual 23 Indian Languages)
Handles WhatsApp voice note (ogg/opus) -> text transcription.

Supports:
- AWS Transcribe batch jobs with explicit LanguageCode (12 langs) or auto IdentifyLanguage with LanguageOptions
- Whisper fallback for unsupported langs (Assamese, Sanskrit, Sindhi, Urdu, etc via IndicWhisper/whisper-large-v3)
- Returns (text, detected_language_code) tuple for downstream LLM language hinting
- Graceful fallback for offline tests (client injection)
"""

import os
import time
import json
import uuid
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Tuple, List


try:
    import boto3
    from botocore.exceptions import (
        BotoCoreError,
        ClientError,
        NoCredentialsError,
        PartialCredentialsError,
        EndpointConnectionError,
    )
except ImportError:
    boto3 = None
    BotoCoreError = ClientError = NoCredentialsError = PartialCredentialsError = EndpointConnectionError = Exception


class TranscribeError(Exception):
    """Base exception for transcription operations."""
    pass


class TranscribeUnavailableError(TranscribeError):
    """Raised when AWS Transcribe or S3 is unreachable / unconfigured."""
    pass


class TranscriptionFailedError(TranscribeError):
    """Raised when transcription job fails or returns empty transcript."""
    pass


# 23 Indian official languages mapping
# AWS supports 12 directly; 4 via Whisper; 6 gap -> fallback to hi-IN with high WER
SUPPORTED_AWS: List[str] = [
    "en-IN", "hi-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN", "or-IN", "ne-NP"
]
# Short code → AWS code
SHORT_TO_AWS: Dict[str, str] = {
    "en": "en-IN", "en-IN": "en-IN",
    "hi": "hi-IN", "hi-IN": "hi-IN",
    "bn": "bn-IN", "bn-IN": "bn-IN",
    "gu": "gu-IN", "gu-IN": "gu-IN",
    "kn": "kn-IN", "kn-IN": "kn-IN",
    "ml": "ml-IN", "ml-IN": "ml-IN",
    "mr": "mr-IN", "mr-IN": "mr-IN",
    "pa": "pa-IN", "pa-IN": "pa-IN",
    "ta": "ta-IN", "ta-IN": "ta-IN",
    "te": "te-IN", "te-IN": "te-IN",
    "or": "or-IN", "or-IN": "or-IN",
    "ne": "ne-NP", "ne-NP": "ne-NP", "ne-IN": "ne-NP",
    "as": "as", "as-IN": "as",  # Whisper only
    "ur": "ur", "ur-IN": "ur",
    "sa": "sa", "sa-IN": "sa",
    "sd": "sd", "sd-IN": "sd",
    "auto": "auto",
}

WHISPER_ONLY = {"as", "as-IN", "sa", "sa-IN", "sd", "sd-IN", "ur", "ur-IN"}
# Gap langs that have zero ASR (bodo, dogri, ks, kok, mai, mni, sat) -> fallback to hi-IN
GAP_LANGS = {"brx", "bodo", "doi", "dogri", "ks", "kok", "konkani", "mai", "maithili", "mni", "sat", "santali", "bodo"}

# Map gap to nearest phonologically close AWS lang for fallback
GAP_FALLBACK: Dict[str, str] = {
    "brx": "hi-IN", "bodo": "hi-IN",
    "doi": "hi-IN", "dogri": "hi-IN",
    "ks": "ur", "kashmiri": "ur",
    "kok": "mr-IN", "konkani": "mr-IN",
    "mai": "hi-IN", "maithili": "hi-IN",
    "mni": "bn-IN", "manipuri": "bn-IN",
    "sat": "bn-IN", "santali": "bn-IN",
    "sanskrit": "hi-IN",
}


def normalize_language_code(code: Optional[str]) -> str:
    if not code or not str(code).strip():
        return os.environ.get("TRANSCRIBE_LANGUAGE", "auto").strip() or "auto"
    c = str(code).strip()
    # Handle case insensitivity
    lower = c.lower()
    if lower == "auto":
        return "auto"
    # Direct match in map
    if c in SHORT_TO_AWS:
        return SHORT_TO_AWS[c]
    if lower in SHORT_TO_AWS:
        return SHORT_TO_AWS[lower]
    # Already full code like hi-IN
    if c.endswith("-IN") or c.endswith("-NP"):
        return c
    # Short code without region
    if len(c) == 2:
        guess = f"{lower}-IN"
        if guess in SUPPORTED_AWS:
            return guess
        return lower  # for whisper like 'as'
    return c


class TranscribeService:
    def __init__(
        self,
        region_name: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        transcribe_client: Optional[Any] = None,
        s3_client: Optional[Any] = None,
        whisper_service: Optional[Any] = None,
    ):
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self.s3_bucket = s3_bucket or os.environ.get("TRANSCRIBE_S3_BUCKET", "")
        self._transcribe_client = transcribe_client
        self._s3_client = s3_client
        self._whisper_service = whisper_service

    def _get_transcribe_client(self):
        if self._transcribe_client is not None:
            return self._transcribe_client
        if boto3 is None:
            raise TranscribeUnavailableError("boto3 library is not available.")
        try:
            self._transcribe_client = boto3.client("transcribe", region_name=self.region_name)
            return self._transcribe_client
        except (NoCredentialsError, PartialCredentialsError) as e:
            raise TranscribeUnavailableError(f"AWS credentials not configured for Transcribe: {str(e)}")
        except Exception as e:
            raise TranscribeUnavailableError(f"Failed to initialize Transcribe client: {str(e)}")

    def _get_s3_client(self):
        if self._s3_client is not None:
            return self._s3_client
        if boto3 is None:
            raise TranscribeUnavailableError("boto3 library is not available.")
        try:
            self._s3_client = boto3.client("s3", region_name=self.region_name)
            return self._s3_client
        except Exception as e:
            raise TranscribeUnavailableError(f"Failed to initialize S3 client: {str(e)}")

    def _get_whisper_service(self):
        if self._whisper_service is not None:
            return self._whisper_service
        # Lazy import to avoid circular deps
        try:
            from services.whisper_service import WhisperService
            self._whisper_service = WhisperService(region_name=self.region_name)
            return self._whisper_service
        except Exception:
            return None

    def _upload_to_s3(self, audio_bytes: bytes, key: str) -> str:
        if not self.s3_bucket:
            raise TranscribeUnavailableError(
                "TRANSCRIBE_S3_BUCKET is not configured. Set env TRANSCRIBE_S3_BUCKET to a writable S3 bucket for voice transcription."
            )
        s3 = self._get_s3_client()
        from services.retry_helper import retry_with_backoff, is_aws_transient_error

        try:
            retry_with_backoff(
                s3.put_object,
                Bucket=self.s3_bucket,
                Key=key,
                Body=audio_bytes,
                ContentType="audio/ogg",
                max_retries=2,
                base_delay=0.2,
                max_delay=2.0,
                is_retryable_fn=is_aws_transient_error,
            )
        except (NoCredentialsError, PartialCredentialsError) as e:
            raise TranscribeUnavailableError(f"AWS credentials not configured for S3: {str(e)}")
        except EndpointConnectionError as e:
            raise TranscribeUnavailableError(f"Could not connect to S3 endpoint: {str(e)}")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            msg = e.response.get("Error", {}).get("Message", str(e))
            raise TranscribeUnavailableError(f"S3 ClientError [{code}]: {msg}")
        except Exception as e:
            raise TranscribeUnavailableError(f"S3 upload failed: {str(e)}")
        return f"s3://{self.s3_bucket}/{key}"

    def _poll_job(self, job_name: str, timeout_seconds: int = 30, poll_interval: float = 1.0) -> Tuple[str, str]:
        transcribe = self._get_transcribe_client()
        start = time.time()
        detected_lang = ""
        while True:
            if time.time() - start > timeout_seconds:
                try:
                    transcribe.delete_transcription_job(TranscriptionJobName=job_name)
                except Exception:
                    pass
                raise TranscriptionFailedError(f"Transcription timed out after {timeout_seconds}s for job {job_name}")

            from services.retry_helper import retry_with_backoff, is_aws_transient_error

            try:
                resp = retry_with_backoff(
                    transcribe.get_transcription_job,
                    TranscriptionJobName=job_name,
                    max_retries=2,
                    base_delay=0.2,
                    max_delay=2.0,
                    is_retryable_fn=is_aws_transient_error,
                )
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "Unknown")
                msg = e.response.get("Error", {}).get("Message", str(e))
                raise TranscribeUnavailableError(f"Transcribe ClientError [{code}]: {msg}")
            except Exception as e:
                raise TranscribeUnavailableError(f"Transcribe get job failed: {str(e)}")

            job = resp.get("TranscriptionJob", {})
            status = job.get("TranscriptionJobStatus", "")
            # Capture detected language if auto
            if job.get("LanguageCode"):
                detected_lang = job.get("LanguageCode", "")
            if status == "COMPLETED":
                uri = job.get("Transcript", {}).get("TranscriptFileUri", "")
                if not uri:
                    raise TranscriptionFailedError("Transcribe job completed but no TranscriptFileUri returned.")
                return uri, detected_lang
            if status == "FAILED":
                reason = job.get("FailureReason", "Unknown failure")
                raise TranscriptionFailedError(f"Transcription failed: {reason}")

            time.sleep(poll_interval)

    def _fetch_transcript_text(self, transcript_uri: str) -> str:
        try:
            with urllib.request.urlopen(transcript_uri) as response:
                data = json.loads(response.read().decode("utf-8"))
            transcripts = data.get("results", {}).get("transcripts", [])
            if not transcripts:
                raise TranscriptionFailedError("Transcribe returned no transcripts.")
            text = transcripts[0].get("transcript", "").strip()
            if not text:
                raise TranscriptionFailedError("Transcribe returned empty transcript (audio may be silent or unintelligible).")
            return text
        except TranscriptionFailedError:
            raise
        except urllib.error.URLError as e:
            raise TranscribeUnavailableError(f"Failed to fetch transcript file: {str(e)}")
        except Exception as e:
            raise TranscriptionFailedError(f"Failed to parse transcript JSON: {str(e)}")

    def transcribe_s3_uri(
        self,
        s3_uri: str,
        language_code: Optional[str] = None,
        media_format: str = "ogg",
        timeout_seconds: int = 30,
    ) -> Tuple[str, str]:
        """
        Transcribes S3 URI via AWS Transcribe or Whisper fallback.
        Returns (transcript_text, detected_language_code)
        """
        if not s3_uri or not s3_uri.strip():
            raise TranscriptionFailedError("S3 URI cannot be empty.")
        raw_code = normalize_language_code(language_code)
        # Whisper-only languages: delegate
        if raw_code in WHISPER_ONLY or raw_code in GAP_LANGS or raw_code in GAP_FALLBACK:
            # Check if whisper provider preferred
            whisper = self._get_whisper_service()
            if whisper is not None:
                try:
                    # Need to download S3 object bytes then whisper
                    # For S3 URI path, we need to fetch bytes via S3
                    try:
                        # Parse s3://bucket/key
                        if s3_uri.startswith("s3://"):
                            path = s3_uri[5:]
                            bucket, key = path.split("/", 1)
                            s3 = self._get_s3_client()
                            obj = s3.get_object(Bucket=bucket, Key=key)
                            audio_bytes = obj["Body"].read()
                            text, detected = whisper.transcribe_audio_bytes(audio_bytes, language_code=raw_code, media_format=media_format)
                            # Also return detected
                            return text, detected or raw_code
                    except Exception:
                        pass
                    # Fallback: try whisper with S3 URI directly
                    text, detected = whisper.transcribe_s3_uri(s3_uri, language_code=raw_code, media_format=media_format, timeout_seconds=timeout_seconds)
                    return text, detected or raw_code
                except Exception as e:
                    # If whisper explicitly unavailable, fall through to AWS fallback mapping
                    fallback = GAP_FALLBACK.get(raw_code.lower(), "hi-IN")
                    if raw_code.lower() not in WHISPER_ONLY:
                        # For gap langs without whisper, fallback to AWS nearest
                        raw_code = fallback
                    else:
                        # Whisper failed but lang is whisper-only -> surface error unless fallback allowed
                        raise TranscribeUnavailableError(f"Whisper unavailable for {raw_code} and no AWS fallback: {str(e)}")
            else:
                # No whisper service configured -> fallback mapping for gap/whisper langs
                if raw_code in WHISPER_ONLY:
                    # Try AWS auto as last resort for Whisper-only langs if whisper not configured
                    # But Urdu etc not in AWS, so this will fail - raise proper error
                    raise TranscribeUnavailableError(f"Language {raw_code} requires Whisper (WHISPER_ENDPOINT_URL not configured). Set WHISPER_ENDPOINT_URL or use supported AWS language.")
                fallback = GAP_FALLBACK.get(raw_code.lower())
                if fallback:
                    raw_code = fallback
                else:
                    raw_code = "auto"

        # Handle gap fallback final normalization
        if raw_code.lower() in GAP_LANGS or raw_code.lower() in GAP_FALLBACK:
            raw_code = GAP_FALLBACK.get(raw_code.lower(), "hi-IN")

        transcribe = self._get_transcribe_client()
        job_name = f"ledgerly-{uuid.uuid4().hex[:12]}-{int(time.time())}"

        try:
            kwargs: Dict[str, Any] = {
                "TranscriptionJobName": job_name,
                "Media": {"MediaFileUri": s3_uri},
                "MediaFormat": media_format,
            }
            if raw_code.lower() == "auto":
                kwargs["IdentifyLanguage"] = True
                # Restrict to supported 12 to improve accuracy vs open
                kwargs["LanguageOptions"] = SUPPORTED_AWS
                # Optionally: kwargs["LanguageIdSettings"] = {code: {"VocabularyName": "..."} } if custom vocab
            else:
                # Ensure code is valid AWS code
                aws_code = SHORT_TO_AWS.get(raw_code, raw_code)
                if aws_code in WHISPER_ONLY:
                    # Should have been handled above, but safety fallback to auto
                    kwargs["IdentifyLanguage"] = True
                    kwargs["LanguageOptions"] = SUPPORTED_AWS
                else:
                    kwargs["LanguageCode"] = aws_code

            from services.retry_helper import retry_with_backoff, is_aws_transient_error

            retry_with_backoff(
                lambda: transcribe.start_transcription_job(**kwargs),
                max_retries=2,
                base_delay=0.2,
                max_delay=2.0,
                is_retryable_fn=is_aws_transient_error,
            )
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            msg = e.response.get("Error", {}).get("Message", str(e))
            raise TranscribeUnavailableError(f"Transcribe start job failed [{code}]: {msg}")
        except Exception as e:
            raise TranscribeUnavailableError(f"Transcribe start job failed: {str(e)}")

        try:
            transcript_uri, detected = self._poll_job(job_name, timeout_seconds=timeout_seconds)
            text = self._fetch_transcript_text(transcript_uri)
            # Use detected lang if auto, else raw_code
            final_lang = detected or raw_code
            if raw_code == "auto" and detected:
                final_lang = detected
            elif raw_code == "auto":
                final_lang = "auto"
            return text, final_lang
        finally:
            try:
                transcribe.delete_transcription_job(TranscriptionJobName=job_name)
            except Exception:
                pass

    def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        media_format: str = "ogg",
        language_code: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> Tuple[str, str]:
        """
        Transcribes audio bytes via S3 transient upload.
        Returns (text, detected_language_code)
        """
        if not audio_bytes or len(audio_bytes) == 0:
            raise TranscriptionFailedError("Audio bytes cannot be empty.")
        max_bytes = int(os.environ.get("MAX_VOICE_BYTES", str(10 * 1024 * 1024)))
        if len(audio_bytes) > max_bytes:
            raise TranscriptionFailedError(f"Audio too large ({len(audio_bytes)} bytes > {max_bytes} bytes). Please send a shorter voice note (<60s).")

        raw_code = normalize_language_code(language_code)

        # Direct whisper path for whisper-only langs to avoid S3+Transcribe roundtrip if provider is whisper-first
        if raw_code in WHISPER_ONLY or raw_code in GAP_LANGS or raw_code.lower() in GAP_FALLBACK:
            whisper = self._get_whisper_service()
            # If whisper endpoint configured, use it directly without S3
            if whisper is not None and whisper.is_configured():
                try:
                    return whisper.transcribe_audio_bytes(audio_bytes, language_code=raw_code, media_format=media_format)
                except Exception as e:
                    # If whisper fails and lang is gap, fallback to AWS nearest
                    fallback = GAP_FALLBACK.get(raw_code.lower())
                    if fallback:
                        raw_code = fallback
                    else:
                        raise e
            elif raw_code in WHISPER_ONLY:
                # Whisper required but not configured
                raise TranscribeUnavailableError(f"Language {raw_code} requires Whisper (WHISPER_ENDPOINT_URL not configured). Configure WHISPER_ENDPOINT_URL or use auto.")

        s3_key = f"whatsapp/{uuid.uuid4().hex[:12]}-{int(time.time())}.{media_format}"
        s3_uri = self._upload_to_s3(audio_bytes, s3_key)
        try:
            # For gap langs now normalized to AWS fallback, pass raw_code
            text, detected = self.transcribe_s3_uri(s3_uri, language_code=raw_code, media_format=media_format, timeout_seconds=timeout_seconds)
            return text, detected
        finally:
            try:
                s3 = self._get_s3_client()
                s3.delete_object(Bucket=self.s3_bucket, Key=s3_key)
            except Exception:
                pass

    # Backward-compatible wrappers that return just text (for existing callers that expect str)
    def transcribe_s3_uri_text(self, *args, **kwargs) -> str:
        text, _ = self.transcribe_s3_uri(*args, **kwargs)
        return text

    def transcribe_audio_bytes_text(self, *args, **kwargs) -> str:
        text, _ = self.transcribe_audio_bytes(*args, **kwargs)
        return text
