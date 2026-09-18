"""
Ledgerly - WhatsApp Cloud API Service
Handles Meta Graph API media download and message sending.
Used for WhatsApp -> voice note -> Transcribe -> Bedrock pipeline.
"""

import os
import json
import hmac
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple


class WhatsAppError(Exception):
    """Base exception for WhatsApp operations."""
    pass


class WhatsAppUnavailableError(WhatsAppError):
    """Raised when Graph API is unreachable or credentials missing."""
    pass


class WhatsAppValidationError(WhatsAppError):
    """Raised when webhook or media payload is invalid."""
    pass


GRAPH_API_VERSION = os.environ.get("WHATSAPP_GRAPH_VERSION", "v18.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class WhatsAppService:
    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        verify_token: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        self.access_token = access_token or os.environ.get("WHATSAPP_TOKEN", "")
        self.phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.verify_token = verify_token or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        self.app_secret = app_secret or os.environ.get("WHATSAPP_APP_SECRET", "")

    # ---------------------------------------------------------------------
    # 1. Webhook verification (GET)
    # ---------------------------------------------------------------------
    def verify_webhook(self, query_params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates Meta webhook verification request.
        Returns (is_valid, challenge_or_error).
        Expected query: hub.mode=subscribe, hub.verify_token, hub.challenge
        """
        mode = query_params.get("hub.mode") or query_params.get("hub_mode") or ""
        token = query_params.get("hub.verify_token") or query_params.get("hub_verify_token") or ""
        challenge = query_params.get("hub.challenge") or query_params.get("hub_challenge") or ""

        if mode != "subscribe":
            return False, "Invalid hub.mode, expected 'subscribe'"
        if not self.verify_token:
            return False, "WHATSAPP_VERIFY_TOKEN is not configured on server"
        if token != self.verify_token:
            return False, "Verify token mismatch"
        if not challenge:
            return False, "Missing hub.challenge"
        return True, str(challenge)

    def verify_signature(self, raw_body: str, signature_header: str) -> bool:
        """
        Verifies X-Hub-Signature-256 HMAC SHA256 if WHATSAPP_APP_SECRET is set.
        If app_secret not configured, returns True (skip verification).
        """
        if not self.app_secret:
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = signature_header.split("=", 1)[1]
        computed = hmac.new(self.app_secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, expected)

    # ---------------------------------------------------------------------
    # 2. Parse inbound webhook (POST)
    # ---------------------------------------------------------------------
    def parse_webhook(self, body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extracts normalized messages from WhatsApp webhook body.
        Returns list of dicts: {from, phone_number_id, message_id, type, text, audio_id, timestamp}
        Supports text and audio/voice messages.
        """
        messages: List[Dict[str, Any]] = []
        try:
            entries = body.get("entry", [])
            if not isinstance(entries, list):
                return messages
            for entry in entries:
                changes = entry.get("changes", []) if isinstance(entry, dict) else []
                for change in changes:
                    value = change.get("value", {}) if isinstance(change, dict) else {}
                    phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
                    if not phone_number_id and self.phone_number_id:
                        phone_number_id = self.phone_number_id
                    raw_msgs = value.get("messages", [])
                    if not isinstance(raw_msgs, list):
                        continue
                    for m in raw_msgs:
                        if not isinstance(m, dict):
                            continue
                        mtype = m.get("type", "")
                        from_number = m.get("from", "")
                        msg_id = m.get("id", "")
                        timestamp = m.get("timestamp", "")
                        entry_obj: Dict[str, Any] = {
                            "from": from_number,
                            "phone_number_id": phone_number_id,
                            "message_id": msg_id,
                            "type": mtype,
                            "timestamp": timestamp,
                        }
                        if mtype == "text":
                            entry_obj["text"] = m.get("text", {}).get("body", "") if isinstance(m.get("text"), dict) else ""
                        elif mtype in ("audio", "voice"):
                            aud = m.get("audio", {}) or m.get("voice", {})
                            if isinstance(aud, dict):
                                entry_obj["audio_id"] = aud.get("id", "")
                                entry_obj["mime_type"] = aud.get("mime_type", "")
                        else:
                            # Include unsupported types for validation downstream
                            entry_obj["raw"] = m
                        messages.append(entry_obj)
        except Exception as e:
            raise WhatsAppValidationError(f"Failed to parse webhook body: {str(e)}")
        return messages

    # ---------------------------------------------------------------------
    # 3. Download media (audio)
    # ---------------------------------------------------------------------
    def download_media(self, media_id: str) -> bytes:
        """
        Downloads media bytes from Graph API via media_id.
        Step 1: GET /{media_id} -> {url}
        Step 2: GET {url} with Bearer token -> bytes
        """
        if not media_id or not media_id.strip():
            raise WhatsAppValidationError("media_id cannot be empty")
        if not self.access_token:
            raise WhatsAppUnavailableError("WHATSAPP_TOKEN is not configured. Set env WHATSAPP_TOKEN for Graph API access.")

        # Step 1: resolve media URL
        media_info_url = f"{GRAPH_BASE}/{media_id.strip()}"
        req = urllib.request.Request(media_info_url, method="GET")
        req.add_header("Authorization", f"Bearer {self.access_token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise WhatsAppUnavailableError(f"Graph API media lookup failed [{e.code}]: {body}")
        except urllib.error.URLError as e:
            raise WhatsAppUnavailableError(f"Graph API connection failed: {str(e)}")
        except Exception as e:
            raise WhatsAppUnavailableError(f"Graph API media lookup error: {str(e)}")

        media_url = data.get("url", "")
        if not media_url:
            raise WhatsAppUnavailableError(f"Graph API did not return media url for id {media_id}: {data}")

        # Step 2: download bytes
        req2 = urllib.request.Request(media_url, method="GET")
        req2.add_header("Authorization", f"Bearer {self.access_token}")
        try:
            with urllib.request.urlopen(req2, timeout=20) as resp2:
                audio_bytes = resp2.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise WhatsAppUnavailableError(f"Graph API media download failed [{e.code}]: {body}")
        except urllib.error.URLError as e:
            raise WhatsAppUnavailableError(f"Graph API media download connection failed: {str(e)}")
        except Exception as e:
            raise WhatsAppUnavailableError(f"Graph API media download error: {str(e)}")

        if not audio_bytes:
            raise WhatsAppUnavailableError("Downloaded media is empty.")

        # Enforce size cap (default 10MB)
        max_bytes = int(os.environ.get("MAX_VOICE_BYTES", str(10 * 1024 * 1024)))
        if len(audio_bytes) > max_bytes:
            raise WhatsAppValidationError(f"Voice note too large ({len(audio_bytes)} bytes > {max_bytes} bytes).")
        return audio_bytes

    # ---------------------------------------------------------------------
    # 4. Send text message
    # ---------------------------------------------------------------------
    def send_text(self, to: str, text: str, phone_number_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends a WhatsApp text message via Graph API.
        Returns parsed JSON response.
        If WHATSAPP_TOKEN not configured, raises WhatsAppUnavailableError (caller may decide to skip).
        """
        if not to or not to.strip():
            raise WhatsAppValidationError("Recipient 'to' cannot be empty")
        if text is None or not str(text).strip():
            raise WhatsAppValidationError("Message text cannot be empty")
        if not self.access_token:
            raise WhatsAppUnavailableError("WHATSAPP_TOKEN is not configured. Cannot send WhatsApp message.")

        pnid = phone_number_id or self.phone_number_id
        if not pnid or not pnid.strip():
            raise WhatsAppValidationError("phone_number_id is not configured. Set WHATSAPP_PHONE_NUMBER_ID.")

        url = f"{GRAPH_BASE}/{pnid.strip()}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to.strip(),
            "type": "text",
            "text": {"preview_url": False, "body": str(text).strip()[:4096]},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.access_token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise WhatsAppUnavailableError(f"WhatsApp send failed [{e.code}]: {body}")
        except urllib.error.URLError as e:
            raise WhatsAppUnavailableError(f"WhatsApp send connection failed: {str(e)}")
        except Exception as e:
            raise WhatsAppUnavailableError(f"WhatsApp send error: {str(e)}")

    def resolve_shop_id(self, phone_number_id: str) -> str:
        """
        Resolves shopId from phone_number_id via env SHOP_PHONE_MAP (JSON) or DEFAULT_SHOP_ID.
        SHOP_PHONE_MAP example: {"1234567890":"shop001","9876543210":"shop002"}
        """
        default_shop = os.environ.get("DEFAULT_SHOP_ID", "shop001")
        map_str = os.environ.get("SHOP_PHONE_MAP", "")
        if map_str:
            try:
                mapping = json.loads(map_str)
                if isinstance(mapping, dict) and phone_number_id in mapping:
                    return str(mapping[phone_number_id]).strip() or default_shop
            except Exception:
                pass
        # Fallback: env PHONE_NUMBER_ID -> SHOP_ID mapping via single value
        return default_shop
