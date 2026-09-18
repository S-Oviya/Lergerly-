"""
Ledgerly - AWS Transcribe Speech-to-Text Service
Handles WhatsApp voice note (ogg/opus) -> text transcription.

Supports:
- S3-stored audio via Transcribe file job (polling)
- Direct bytes via S3 transient upload if bucket configured
- Graceful fallbacks for offline tests (client injection)
"""

import os
import time
import json
import uuid
import urllib.request
import urllib.error
from typing import Any, Dict, Optional


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


class TranscribeService:
    def __init__(
        self,
        region_name: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        transcribe_client: Optional[Any] = None,
        s3_client: Optional[Any] = None,
    ):
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self.s3_bucket = s3_bucket or os.environ.get("TRANSCRIBE_S3_BUCKET", "")
        self._transcribe_client = transcribe_client
        self._s3_client = s3_client

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

    def _upload_to_s3(self, audio_bytes: bytes, key: str) -> str:
        if not self.s3_bucket:
            raise TranscribeUnavailableError(
                "TRANSCRIBE_S3_BUCKET is not configured. Set env TRANSCRIBE_S3_BUCKET to a writable S3 bucket for voice transcription."
            )
        s3 = self._get_s3_client()
        try:
            s3.put_object(Bucket=self.s3_bucket, Key=key, Body=audio_bytes, ContentType="audio/ogg")
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

    def _poll_job(self, job_name: str, timeout_seconds: int = 30, poll_interval: float = 1.0) -> str:
        transcribe = self._get_transcribe_client()
        start = time.time()
        while True:
            if time.time() - start > timeout_seconds:
                try:
                    transcribe.delete_transcription_job(TranscriptionJobName=job_name)
                except Exception:
                    pass
                raise TranscriptionFailedError(f"Transcription timed out after {timeout_seconds}s for job {job_name}")

            try:
                resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "Unknown")
                msg = e.response.get("Error", {}).get("Message", str(e))
                raise TranscribeUnavailableError(f"Transcribe ClientError [{code}]: {msg}")
            except Exception as e:
                raise TranscribeUnavailableError(f"Transcribe get job failed: {str(e)}")

            status = resp.get("TranscriptionJob", {}).get("TranscriptionJobStatus", "")
            if status == "COMPLETED":
                uri = resp.get("TranscriptionJob", {}).get("Transcript", {}).get("TranscriptFileUri", "")
                if not uri:
                    raise TranscriptionFailedError("Transcribe job completed but no TranscriptFileUri returned.")
                return uri
            if status == "FAILED":
                reason = resp.get("TranscriptionJob", {}).get("FailureReason", "Unknown failure")
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
    ) -> str:
        if not s3_uri or not s3_uri.strip():
            raise TranscriptionFailedError("S3 URI cannot be empty.")
        language_code = language_code or os.environ.get("TRANSCRIBE_LANGUAGE", "en-IN")
        transcribe = self._get_transcribe_client()
        job_name = f"ledgerly-{uuid.uuid4().hex[:12]}-{int(time.time())}"

        try:
            kwargs: Dict[str, Any] = {
                "TranscriptionJobName": job_name,
                "Media": {"MediaFileUri": s3_uri},
                "MediaFormat": media_format,
                "LanguageCode": language_code,
            }
            # Enable automatic language identification if requested
            if language_code.lower() == "auto":
                kwargs.pop("LanguageCode", None)
                kwargs["IdentifyLanguage"] = True

            transcribe.start_transcription_job(**kwargs)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            msg = e.response.get("Error", {}).get("Message", str(e))
            raise TranscribeUnavailableError(f"Transcribe start job failed [{code}]: {msg}")
        except Exception as e:
            raise TranscribeUnavailableError(f"Transcribe start job failed: {str(e)}")

        try:
            transcript_uri = self._poll_job(job_name, timeout_seconds=timeout_seconds)
            text = self._fetch_transcript_text(transcript_uri)
            return text
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
    ) -> str:
        if not audio_bytes or len(audio_bytes) == 0:
            raise TranscriptionFailedError("Audio bytes cannot be empty.")
        # WhatsApp limit ~5MB for Lambda friendly; enforce 10MB cap
        max_bytes = int(os.environ.get("MAX_VOICE_BYTES", str(10 * 1024 * 1024)))
        if len(audio_bytes) > max_bytes:
            raise TranscriptionFailedError(f"Audio too large ({len(audio_bytes)} bytes > {max_bytes} bytes). Please send a shorter voice note (<60s).")

        s3_key = f"whatsapp/{uuid.uuid4().hex[:12]}-{int(time.time())}.{media_format}"
        s3_uri = self._upload_to_s3(audio_bytes, s3_key)
        try:
            text = self.transcribe_s3_uri(s3_uri, language_code=language_code, media_format=media_format, timeout_seconds=timeout_seconds)
            return text
        finally:
            # Cleanup S3 object
            try:
                s3 = self._get_s3_client()
                s3.delete_object(Bucket=self.s3_bucket, Key=s3_key)
            except Exception:
                pass
