"""
Ledgerly - AWS Lambda Ingestion, Bedrock Extraction & DynamoDB Data Layer Handler
Phase 3: Amazon Bedrock Natural-Language Extraction + REST Operations
"""

import os
import sys
import json
import re
import base64
import urllib.parse
from decimal import Decimal
from typing import Any, Dict, Tuple, Optional

# Ensure services directory is resolvable in Lambda and local test runs
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from services.ledger_service import (
    LedgerService,
    DynamoDBUnavailableError,
    LedgerValidationError,
)
from services.bedrock_service import (
    BedrockService,
    BedrockUnavailableError,
    BedrockExtractionError,
    detect_language_from_text,
)
from services.transcribe_service import (
    TranscribeService,
    TranscribeUnavailableError,
    TranscriptionFailedError,
    normalize_language_code,
    SUPPORTED_AWS,
)
from services.whatsapp_service import (
    WhatsAppService,
    WhatsAppUnavailableError,
    WhatsAppValidationError,
)
from services.payment_reply_service import PaymentReplyService
try:
    from services.whisper_service import WhisperService, WhisperUnavailableError, WhisperTranscriptionFailedError
except ImportError:
    WhisperService = None
    WhisperUnavailableError = WhisperTranscriptionFailedError = Exception

# Shared service instances
ledger_service = LedgerService()
bedrock_service = BedrockService()
whatsapp_service = WhatsAppService()
transcribe_service = TranscribeService()
payment_reply_service = PaymentReplyService()


def _build_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constructs an API Gateway compatible HTTP response dictionary with CORS headers.
    """
    def _json_default(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return str(obj)

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(payload, default=_json_default),
    }


def _extract_and_validate_body(event: Dict[str, Any]) -> Tuple[bool, Any, int]:
    """
    Extracts and parses JSON body from the incoming API Gateway event.
    Returns: (is_valid, parsed_body_or_error_dict, status_code)
    """
    if not isinstance(event, dict):
        return False, {"success": False, "error": "Invalid event structure"}, 400

    raw_body = event.get("body")
    if raw_body is None:
        return False, {"success": False, "error": "Missing request body"}, 400

    if isinstance(raw_body, dict):
        parsed_body = raw_body
    elif isinstance(raw_body, str):
        if event.get("isBase64Encoded", False):
            try:
                raw_body = base64.b64decode(raw_body).decode("utf-8")
            except Exception:
                return False, {"success": False, "error": "Failed to decode base64 body"}, 400

        stripped_body = raw_body.strip()
        if not stripped_body:
            return False, {"success": False, "error": "Request body cannot be empty"}, 400

        try:
            parsed_body = json.loads(stripped_body)
        except (json.JSONDecodeError, TypeError):
            return False, {"success": False, "error": "Invalid JSON format"}, 400
    else:
        return False, {"success": False, "error": "Unsupported request body type"}, 400

    if not isinstance(parsed_body, dict):
        return False, {"success": False, "error": "Request body must be a JSON object"}, 400

    return True, parsed_body, 200


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Main AWS Lambda entry point supporting:
    - GET  /whatsapp/webhook  : Meta webhook verification (hub.challenge)
    - POST /whatsapp/webhook  : WhatsApp inbound (text/voice) -> STT -> Bedrock -> Ledger -> WhatsApp reply
    - POST /whatsapp/transcribe: Direct audio -> Transcribe (testing)
    - POST /message (or legacy POST without route): natural language note -> Bedrock extraction
    - POST /customers: create customer
    - GET /customers: list customers (requires ?shopId=...)
    - GET /customers/{customerId}: get single customer
    - POST /transactions: record transaction (CREDIT or PAYMENT)
    - GET /customers/{customerId}/transactions: list customer transactions
    """
    if not isinstance(event, dict):
        return _build_response(400, {"success": False, "error": "Invalid event payload"})

    # 1. CORS Preflight
    http_method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "POST")
    ).upper()

    if http_method == "OPTIONS":
        return _build_response(200, {"success": True, "status": "preflight_ok"})

    # Determine route path
    path = event.get("path") or event.get("rawPath") or ""
    path = path.rstrip("/") if path != "/" else "/"
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}

    # ---------------------------------------------------------------------
    # Helpers for WhatsApp -> STT -> LLM -> Ledger
    # ---------------------------------------------------------------------
    def _resolve_shop_id(phone_number_id: str) -> str:
        return whatsapp_service.resolve_shop_id(phone_number_id or "")

    def _find_or_create_customer(shop_id: str, customer_name: str, fallback_phone: str, preferred_language: Optional[str] = None) -> Dict[str, Any]:
        """Finds existing customer by name (case-insensitive incl. unicode) or creates new one with language."""
        try:
            customers = ledger_service.list_customers(shop_id)
        except Exception:
            customers = []
        normalized = customer_name.strip().lower()
        # Exact case-insensitive match first (unicode-safe)
        for c in customers:
            if str(c.get("name", "")).strip().lower() == normalized:
                # Update preferredLanguage if we have new hint
                if preferred_language and c.get("preferredLanguage") != preferred_language:
                    try:
                        # Best-effort update via ledger_service if method exists
                        if hasattr(ledger_service, "update_customer_language"):
                            ledger_service.update_customer_language(c.get("customerId"), preferred_language)
                    except Exception:
                        pass
                return c
        # Fuzzy first-token match (supports multilingual names)
        first_in = normalized.split()[0] if normalized.split() else ""
        for c in customers:
            cname = str(c.get("name", "")).strip().lower()
            first_c = cname.split()[0] if cname.split() else ""
            if first_in and first_c and first_in == first_c:
                return c
        # Create new
        phone = fallback_phone.strip() if fallback_phone and fallback_phone.strip() else "+91 00000 00000"
        # Try to create with preferredLanguage if ledger supports it
        try:
            return ledger_service.create_customer(shop_id=shop_id, name=customer_name.strip(), phone=phone, preferred_language=preferred_language)
        except TypeError:
            # Fallback for older signature
            cust = ledger_service.create_customer(shop_id=shop_id, name=customer_name.strip(), phone=phone)
            # Attempt to set language separately
            if preferred_language and hasattr(ledger_service, "update_customer_language"):
                try:
                    ledger_service.update_customer_language(cust.get("customerId"), preferred_language)
                except Exception:
                    pass
            return cust

    def _find_customer_by_phone(shop_id: str, phone: str) -> Optional[Dict[str, Any]]:
        """Finds existing customer by phone number under shop_id."""
        if not phone or not phone.strip():
            return None
        try:
            customers = ledger_service.list_customers(shop_id)
        except Exception:
            customers = []
        clean_p = re.sub(r"\D", "", phone)
        for c in customers:
            c_phone = re.sub(r"\D", "", str(c.get("phone", "")))
            if clean_p and c_phone:
                if clean_p == c_phone or (len(clean_p) >= 10 and len(c_phone) >= 10 and clean_p[-10:] == c_phone[-10:]):
                    return c
        return None

    def _process_whatsapp_single_message(msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes a single WhatsApp message (text or audio) through multilingual STT -> Bedrock -> Ledger.
        Supports 23 Indian languages (auto detection via Transcribe IdentifyLanguage + Whisper fallback).
        Returns result dict for response aggregation.
        """
        from_number = msg.get("from", "")
        phone_number_id = msg.get("phone_number_id", "")
        msg_id = msg.get("message_id", "")
        mtype = msg.get("type", "")
        shop_id = _resolve_shop_id(phone_number_id)
        # Language hint may come from msg (for testing) or env default
        hint_lang = msg.get("language_code") or msg.get("language") or msg.get("lang")
        env_default_lang = os.environ.get("TRANSCRIBE_LANGUAGE", "auto")
        if not hint_lang:
            hint_lang = env_default_lang

        # 1. Extract raw text + detected language
        raw_text = ""
        detected_lang = hint_lang  # will be updated after STT if auto
        transcription_meta: Dict[str, Any] = {}
        if hint_lang:
            transcription_meta["requested_language"] = hint_lang
        if mtype == "text":
            raw_text = str(msg.get("text", "")).strip()
            if not raw_text:
                return {"message_id": msg_id, "status": "failed", "error": "Empty text message", "from": from_number}
            # For text, if hint is auto or empty, detect from script
            if not hint_lang or str(hint_lang).strip().lower() == "auto":
                detected_lang = detect_language_from_text(raw_text)
            else:
                detected_lang = normalize_language_code(hint_lang)
            transcription_meta["detected_language"] = detected_lang
            transcription_meta["source"] = "text"
            transcription_meta["language_detection"] = "script_heuristic" if (not hint_lang or str(hint_lang).lower()=="auto") else "explicit_hint"
        elif mtype in ("audio", "voice"):
            audio_id = msg.get("audio_id", "")
            if not audio_id:
                return {"message_id": msg_id, "status": "failed", "error": "Missing audio id", "from": from_number}
            try:
                audio_bytes = whatsapp_service.download_media(audio_id)
                transcription_meta["audio_bytes_len"] = len(audio_bytes)
                mime = str(msg.get("mime_type", "audio/ogg")).lower()
                media_format = "ogg"
                if "mpeg" in mime or "mp3" in mime:
                    media_format = "mp3"
                elif "mp4" in mime:
                    media_format = "mp4"
                elif "wav" in mime:
                    media_format = "wav"
                # Use hint_lang or auto
                lang_for_stt = hint_lang or env_default_lang or "auto"
                # transcribe_service now returns (text, detected_lang)
                result = transcribe_service.transcribe_audio_bytes(audio_bytes, media_format=media_format, language_code=lang_for_stt)
                if isinstance(result, tuple) and len(result) == 2:
                    raw_text, detected_lang = result
                elif isinstance(result, str):
                    raw_text = result
                    detected_lang = normalize_language_code(lang_for_stt)
                else:
                    raw_text = str(result)
                    detected_lang = normalize_language_code(lang_for_stt)
                # If auto but transcript has native script, heuristic overwrites
                if not detected_lang or str(detected_lang).lower() == "auto":
                    heuristic = detect_language_from_text(raw_text)
                    if heuristic != "en-IN" or not detected_lang:
                        detected_lang = heuristic
                        transcription_meta["language_detection"] = "script_heuristic_post_stt"
                transcription_meta["transcript"] = raw_text
                transcription_meta["detected_language"] = detected_lang
                transcription_meta["source"] = "transcribe"
                transcription_meta["stt_provider"] = "transcribe" if detected_lang in SUPPORTED_AWS or detected_lang == "auto" else "whisper_fallback"
            except (TranscriptionFailedError, WhatsAppValidationError, WhisperTranscriptionFailedError) as e:
                error_msg = str(e)
                try:
                    # Multilingual error reply via fallback template if possible
                    fallback_lang = normalize_language_code(hint_lang) if hint_lang else "hi-IN"
                    err_reply = bedrock_service.get_fallback_reply({"customerName": "Customer","type":"CREDIT","amount":0}, 0, language_code=fallback_lang)
                    # Use generic voice failure in user's lang
                    whatsapp_service.send_text(from_number, f"Voice note samajh nahi paya: {error_msg}. Kripya dobara bhejein ya text me likhein. 🙏", phone_number_id)
                except Exception:
                    pass
                return {"message_id": msg_id, "status": "failed", "error": f"Transcription failed: {error_msg}", "from": from_number, "shopId": shop_id, "requested_language": hint_lang}
            except (TranscribeUnavailableError, WhisperUnavailableError, WhatsAppUnavailableError) as e:
                error_msg = str(e)
                return {"message_id": msg_id, "status": "error", "error": f"Service unavailable: {error_msg}", "from": from_number, "shopId": shop_id, "code": 503, "requested_language": hint_lang}
            except Exception as e:
                return {"message_id": msg_id, "status": "error", "error": f"Transcription error: {str(e)}", "from": from_number, "shopId": shop_id, "code": 503}
        else:
            return {"message_id": msg_id, "status": "skipped", "error": f"Unsupported message type '{mtype}'", "from": from_number}

        if not raw_text or not raw_text.strip():
            return {"message_id": msg_id, "status": "failed", "error": "Transcript/text is empty", "from": from_number, "detected_language": detected_lang}

        # Normalize detected language for Bedrock; if still auto, detect from text
        if not detected_lang or str(detected_lang).lower() == "auto":
            detected_lang = detect_language_from_text(raw_text)
        norm_lang = normalize_language_code(detected_lang) if detected_lang else "auto"
        # Avoid storing 'auto' in ledger; keep specific
        if norm_lang.lower() == "auto":
            norm_lang = detect_language_from_text(raw_text)

        # -----------------------------------------------------------------
        # 1.5 Check for customer payment reply (e.g. "I paid ₹500")
        # -----------------------------------------------------------------
        supplied_name = msg.get("customerName") or msg.get("name") or msg.get("sender_name")
        payment_check = payment_reply_service.parse(
            raw_text.strip(),
            customer_name=supplied_name,
            language=norm_lang,
        )

        if payment_check is not None:
            if payment_check.get("action") == "AMBIGUOUS":
                # Ambiguous payment message (e.g. "paid", "settled", "paid 0") -> request clarification
                clarification = "Please specify the payment amount (e.g. 'I paid ₹500')."
                if norm_lang and norm_lang.startswith("hi"):
                    clarification = "Kripya bhugtan ki rakam batayein (jaise: 'paid 500'). 🙏"
                wa_send_status = "skipped"
                wa_response = None
                try:
                    if whatsapp_service.access_token and from_number:
                        wa_response = whatsapp_service.send_text(from_number, clarification, phone_number_id)
                        wa_send_status = "sent"
                    else:
                        wa_send_status = "skipped_no_token"
                except Exception as e:
                    wa_send_status = f"failed: {str(e)}"

                ambiguous_res: Dict[str, Any] = {
                    "message_id": msg_id,
                    "status": "ambiguous",
                    "from": from_number,
                    "shopId": shop_id,
                    "type": mtype,
                    "transcript": raw_text,
                    "detected_language": norm_lang,
                    "paymentIntent": payment_check,
                    "reply": clarification,
                    "whatsapp_send": wa_send_status,
                }
                if wa_response:
                    ambiguous_res["whatsapp_response"] = wa_response
                if transcription_meta:
                    ambiguous_res["transcription_meta"] = transcription_meta
                return ambiguous_res

            if payment_check.get("action") == "PAYMENT":
                # Identify customer using existing customer lookup mechanisms
                customer = _find_customer_by_phone(shop_id, from_number)
                if not customer:
                    cust_name = supplied_name or (f"Customer ({from_number})" if from_number else "Customer")
                    customer = _find_or_create_customer(shop_id, cust_name, from_number, preferred_language=norm_lang)
                customer_id = customer.get("customerId", "")

                # Idempotency check using msg_id to prevent duplicate payment transactions
                payment_tx_id = f"wa_{msg_id}" if msg_id else None
                existing_tx = None
                if payment_tx_id:
                    try:
                        customer_txs = ledger_service.get_customer_transactions(customer_id, shop_id=shop_id)
                        existing_tx = next((t for t in customer_txs if t.get("transactionId") == payment_tx_id), None)
                    except Exception:
                        existing_tx = None

                is_duplicate = False
                if existing_tx:
                    transaction = existing_tx
                    balance = ledger_service.calculate_customer_balance(customer_id, shop_id=shop_id)
                    is_duplicate = True
                else:
                    # Record PAYMENT transaction in ledger
                    payment_amount = payment_check["amount"]
                    try:
                        transaction = ledger_service.add_transaction(
                            shop_id=shop_id,
                            customer_id=customer_id,
                            tx_type="PAYMENT",
                            amount=payment_amount,
                            description="Customer payment via WhatsApp",
                            transaction_id=payment_tx_id,
                            language=norm_lang,
                        )
                        balance = transaction.get("updatedCustomerBalance", 0)
                    except TypeError as te:
                        if "language" in str(te):
                            transaction = ledger_service.add_transaction(
                                shop_id=shop_id,
                                customer_id=customer_id,
                                tx_type="PAYMENT",
                                amount=payment_amount,
                                description="Customer payment via WhatsApp",
                                transaction_id=payment_tx_id,
                            )
                            balance = transaction.get("updatedCustomerBalance", 0)
                        else:
                            code = 503 if isinstance(te, DynamoDBUnavailableError) else 400
                            return {"message_id": msg_id, "status": "error" if code == 503 else "failed", "error": str(te), "from": from_number, "paymentIntent": payment_check, "transcript": raw_text, "code": code, "detected_language": norm_lang}
                    except (LedgerValidationError, DynamoDBUnavailableError) as e:
                        code = 503 if isinstance(e, DynamoDBUnavailableError) else 400
                        return {"message_id": msg_id, "status": "error" if code == 503 else "failed", "error": str(e), "from": from_number, "paymentIntent": payment_check, "transcript": raw_text, "code": code, "detected_language": norm_lang}
                    except Exception as e:
                        return {"message_id": msg_id, "status": "error", "error": f"Ledger error: {str(e)}", "from": from_number, "paymentIntent": payment_check, "transcript": raw_text, "detected_language": norm_lang}

                # Generate concise WhatsApp acknowledgment with deterministic balance
                extracted_for_reply = {
                    "customerName": customer.get("name", "Customer"),
                    "type": "PAYMENT",
                    "amount": payment_check["amount"],
                    "description": "Customer payment via WhatsApp",
                }
                try:
                    reply_text = bedrock_service.generate_reply(extracted_for_reply, balance, raw_text, language_code=norm_lang)
                except Exception:
                    try:
                        reply_text = bedrock_service.get_fallback_reply(extracted_for_reply, balance, language_code=norm_lang)
                    except Exception:
                        reply_text = f"Payment of ₹{payment_check['amount']} recorded. Your remaining balance is ₹{balance}."

                # Send WhatsApp acknowledgment
                wa_send_status = "skipped"
                wa_response = None
                try:
                    if whatsapp_service.access_token and from_number:
                        wa_response = whatsapp_service.send_text(from_number, reply_text, phone_number_id)
                        wa_send_status = "sent"
                    else:
                        wa_send_status = "skipped_no_token"
                except (WhatsAppUnavailableError, WhatsAppValidationError) as e:
                    wa_send_status = f"failed: {str(e)}"
                except Exception as e:
                    wa_send_status = f"failed: {str(e)}"

                payment_res: Dict[str, Any] = {
                    "message_id": msg_id,
                    "status": "processed",
                    "from": from_number,
                    "shopId": shop_id,
                    "type": mtype,
                    "transcript": raw_text,
                    "detected_language": norm_lang,
                    "paymentIntent": payment_check,
                    "customer": {"customerId": customer.get("customerId"), "name": customer.get("name")},
                    "transaction": transaction,
                    "balance": balance,
                    "reply": reply_text,
                    "reply_language": norm_lang,
                    "whatsapp_send": wa_send_status,
                }
                if is_duplicate:
                    payment_res["duplicate"] = True
                if wa_response:
                    payment_res["whatsapp_response"] = wa_response
                if transcription_meta:
                    payment_res["transcription_meta"] = transcription_meta
                return payment_res

        # 2. Bedrock extraction with language hint
        try:
            extracted = bedrock_service.extract_transaction(raw_text.strip(), language_code=norm_lang)
        except BedrockExtractionError as e:
            try:
                # Send error in detected language if possible
                whatsapp_service.send_text(from_number, f"Samajh nahi paya: {str(e)}. Kripya naam, rakam aur udhar/jama sahi se bhejein. 🙏", phone_number_id)
            except Exception:
                pass
            return {"message_id": msg_id, "status": "failed", "error": f"Extraction failed: {str(e)}", "from": from_number, "transcript": raw_text, "shopId": shop_id, "detected_language": norm_lang}
        except BedrockUnavailableError as e:
            return {"message_id": msg_id, "status": "error", "error": f"Bedrock unavailable: {str(e)}", "from": from_number, "transcript": raw_text, "code": 503, "detected_language": norm_lang}

        # 3. Ledger: find or create customer, add transaction with language & idempotency
        try:
            customer = _find_or_create_customer(shop_id, extracted["customerName"], from_number, preferred_language=norm_lang)
            customer_id = customer.get("customerId", "")

            # Idempotency check using msg_id to prevent duplicate transactions
            tx_id = f"wa_{msg_id}" if msg_id else None
            existing_tx = None
            if tx_id:
                try:
                    customer_txs = ledger_service.get_customer_transactions(customer_id, shop_id=shop_id)
                    existing_tx = next((t for t in customer_txs if t.get("transactionId") == tx_id), None)
                    if not existing_tx and hasattr(ledger_service, "get_transaction"):
                        existing_tx = ledger_service.get_transaction(tx_id)
                except Exception:
                    existing_tx = None

            is_duplicate = False
            if existing_tx:
                transaction = existing_tx
                balance = ledger_service.calculate_customer_balance(customer_id, shop_id=shop_id)
                is_duplicate = True
            else:
                transaction = ledger_service.add_transaction(
                    shop_id=shop_id,
                    customer_id=customer_id,
                    tx_type=extracted["type"],
                    amount=extracted["amount"],
                    description=extracted.get("description", ""),
                    transaction_id=tx_id,
                    language=norm_lang,
                )
                balance = transaction.get("updatedCustomerBalance", 0)
        except TypeError as e:
            # Retry without language if signature mismatch
            if "language" in str(e) or "transaction_id" in str(e):
                try:
                    transaction = ledger_service.add_transaction(
                        shop_id=shop_id,
                        customer_id=customer_id,
                        tx_type=extracted["type"],
                        amount=extracted["amount"],
                        description=extracted.get("description", ""),
                        transaction_id=tx_id,
                    )
                    balance = transaction.get("updatedCustomerBalance", 0)
                except Exception as e2:
                    code = 503 if isinstance(e2, DynamoDBUnavailableError) else 400
                    return {"message_id": msg_id, "status": "error" if code == 503 else "failed", "error": str(e2), "from": from_number, "extracted": extracted, "transcript": raw_text, "code": code, "detected_language": norm_lang}
            else:
                code = 503 if isinstance(e, DynamoDBUnavailableError) else 400
                return {"message_id": msg_id, "status": "error" if code == 503 else "failed", "error": str(e), "from": from_number, "extracted": extracted, "transcript": raw_text, "code": code, "detected_language": norm_lang}
        except (LedgerValidationError, DynamoDBUnavailableError) as e:
            code = 503 if isinstance(e, DynamoDBUnavailableError) else 400
            return {"message_id": msg_id, "status": "error" if code == 503 else "failed", "error": str(e), "from": from_number, "extracted": extracted, "transcript": raw_text, "code": code, "detected_language": norm_lang}
        except Exception as e:
            return {"message_id": msg_id, "status": "error", "error": f"Ledger error: {str(e)}", "from": from_number, "extracted": extracted, "transcript": raw_text, "detected_language": norm_lang}

        # 4. Generate reply in detected language
        try:
            reply_text = bedrock_service.generate_reply(extracted, balance, raw_text, language_code=norm_lang)
        except Exception:
            try:
                reply_text = bedrock_service.get_fallback_reply(extracted, balance, language_code=norm_lang)
            except Exception:
                typ = extracted.get("type", "")
                amt = extracted.get("amount", "")
                reply_text = f"{extracted.get('customerName')} ke liye {amt} ({typ}) record kiya. Balance: {balance}. ✅"

        # 5. Send WhatsApp reply (best-effort)
        wa_send_status = "skipped"
        wa_response = None
        try:
            if whatsapp_service.access_token and from_number:
                wa_response = whatsapp_service.send_text(from_number, reply_text, phone_number_id)
                wa_send_status = "sent"
            else:
                wa_send_status = "skipped_no_token"
        except (WhatsAppUnavailableError, WhatsAppValidationError) as e:
            wa_send_status = f"failed: {str(e)}"
        except Exception as e:
            wa_send_status = f"failed: {str(e)}"

        result: Dict[str, Any] = {
            "message_id": msg_id,
            "status": "processed",
            "from": from_number,
            "shopId": shop_id,
            "type": mtype,
            "transcript": raw_text,
            "detected_language": norm_lang,
            "extractedTransaction": extracted,
            "customer": {"customerId": customer.get("customerId"), "name": customer.get("name")},
            "transaction": transaction,
            "balance": balance,
            "reply": reply_text,
            "reply_language": norm_lang,
            "whatsapp_send": wa_send_status,
        }
        if is_duplicate:
            result["duplicate"] = True
        if wa_response:
            result["whatsapp_response"] = wa_response
        if transcription_meta:
            result["transcription_meta"] = transcription_meta
        return result

    try:
        # ---------------------------------------------------------------------
        # ROUTE: GET /whatsapp/webhook (verification)
        # ---------------------------------------------------------------------
        if path in ("/whatsapp/webhook", "/whatsapp") and http_method == "GET":
            # Support both queryStringParameters and raw query parsing
            challenge = query_params.get("hub.challenge") or query_params.get("hub_challenge") or ""
            mode = query_params.get("hub.mode") or query_params.get("hub_mode") or ""
            token = query_params.get("hub.verify_token") or query_params.get("hub_verify_token") or ""
            # Fallback: parse raw query string if API Gateway uses different shape
            if not challenge and event.get("rawQueryString"):
                try:
                    qs = urllib.parse.parse_qs(event.get("rawQueryString", ""))
                    challenge = qs.get("hub.challenge", [""])[0]
                    mode = qs.get("hub.mode", [""])[0]
                    token = qs.get("hub.verify_token", [""])[0]
                except Exception:
                    pass
            # Use service verification
            qp = {"hub.mode": mode, "hub.verify_token": token, "hub.challenge": challenge}
            ok, result = whatsapp_service.verify_webhook(qp)
            if ok:
                # Must return challenge as plain text per Meta spec; support both text and JSON for testing
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "text/plain",
                        "Access-Control-Allow-Origin": "*",
                    },
                    "body": result,
                }
            else:
                return _build_response(403, {"success": False, "error": result})

        # ---------------------------------------------------------------------
        # ROUTE: POST /whatsapp/webhook (inbound WhatsApp messages)
        # ---------------------------------------------------------------------
        if path in ("/whatsapp/webhook", "/whatsapp") and http_method == "POST":
            # Optional signature verification
            raw_body_str = ""
            if isinstance(event.get("body"), str):
                raw_body_str = event.get("body") or ""
                if event.get("isBase64Encoded"):
                    try:
                        raw_body_str = base64.b64decode(raw_body_str).decode("utf-8")
                    except Exception:
                        pass
            elif isinstance(event.get("body"), dict):
                raw_body_str = json.dumps(event.get("body"))
            sig = event.get("headers", {}).get("X-Hub-Signature-256") or event.get("headers", {}).get("x-hub-signature-256") or ""
            if sig and not whatsapp_service.verify_signature(raw_body_str, sig):
                return _build_response(403, {"success": False, "error": "Invalid X-Hub-Signature-256"})

            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                # WhatsApp always expects 200 to avoid retries, but for validation we return 400 for direct API callers
                # Check if this is a real WhatsApp webhook (has entry->changes)
                has_whatsapp_shape = isinstance(body, dict) and isinstance(body.get("entry"), list) if isinstance(body, dict) else False
                if has_whatsapp_shape:
                    return _build_response(200, {"success": True, "status": "ignored", "reason": body.get("error", "Invalid body shape")})
                return _build_response(status_code, body)

            # Parse messages (empty list means status updates, delivery receipts -> ack)
            try:
                parsed_messages = whatsapp_service.parse_webhook(body)
            except WhatsAppValidationError as e:
                return _build_response(200, {"success": True, "status": "ignored", "reason": str(e)})

            if not parsed_messages:
                return _build_response(200, {"success": True, "status": "received", "processed": 0, "reason": "No messages in webhook (likely status update)"})

            results = []
            for m in parsed_messages:
                res = _process_whatsapp_single_message(m)
                results.append(res)

            # Determine overall HTTP status: if all 503 -> 503 for observability, else 200 (WhatsApp expects 200)
            # For Graph API webhook, we must return 200 to stop retries, even on internal errors.
            is_whatsapp_webhook = True
            # Heuristic: if request came from Graph API, it will have entry field
            if body.get("object") == "whatsapp_business_account" or body.get("entry"):
                # Always 200 for WhatsApp to ack
                return _build_response(200, {"success": True, "status": "processed", "count": len(results), "results": results})
            # For direct API test callers, surface first error code if any 503
            has_503 = any(r.get("code") == 503 for r in results)
            if has_503:
                return _build_response(200, {"success": True, "status": "processed_with_unavailable", "count": len(results), "results": results})
            return _build_response(200, {"success": True, "status": "processed", "count": len(results), "results": results})

        # ---------------------------------------------------------------------
        # ROUTE: POST /whatsapp/transcribe (direct audio->text for testing without WhatsApp)
        # Multilingual: supports all 23 languages via auto or explicit code; returns detected language
        # ---------------------------------------------------------------------
        if path == "/whatsapp/transcribe" and http_method == "POST":
            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                return _build_response(status_code, body)
            s3_uri = body.get("s3_uri") or body.get("s3Uri") or ""
            audio_b64 = body.get("audio_base64") or body.get("audioBase64") or ""
            media_format = body.get("media_format") or body.get("mediaFormat") or "ogg"
            language_code = body.get("language_code") or body.get("languageCode") or body.get("language") or None
            # Normalize hint
            if language_code:
                language_code = normalize_language_code(language_code)
            try:
                if s3_uri and s3_uri.strip():
                    result = transcribe_service.transcribe_s3_uri(s3_uri.strip(), language_code=language_code, media_format=media_format)
                    if isinstance(result, tuple):
                        text, detected = result
                    else:
                        text, detected = str(result), normalize_language_code(language_code or "auto")
                elif audio_b64 and audio_b64.strip():
                    import base64 as _b64
                    audio_bytes = _b64.b64decode(audio_b64.strip())
                    result = transcribe_service.transcribe_audio_bytes(audio_bytes, media_format=media_format, language_code=language_code)
                    if isinstance(result, tuple):
                        text, detected = result
                    else:
                        text, detected = str(result), normalize_language_code(language_code or "auto")
                else:
                    return _build_response(400, {"success": False, "error": "Provide either 's3_uri' or 'audio_base64'"})
                return _build_response(200, {"success": True, "transcript": text, "detected_language": detected, "requested_language": language_code or "auto"})
            except (TranscriptionFailedError, TranscribeUnavailableError, WhisperUnavailableError, WhisperTranscriptionFailedError) as e:
                code = 503 if isinstance(e, (TranscribeUnavailableError, WhisperUnavailableError)) else 400
                return _build_response(code, {"success": False, "error": str(e), "requested_language": language_code})
            except Exception as e:
                return _build_response(500, {"success": False, "error": "Transcription error", "details": str(e)})

        # ---------------------------------------------------------------------
        # ROUTE: POST /customers
        # ---------------------------------------------------------------------
        if http_method == "POST" and path == "/customers":
            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                return _build_response(status_code, body)

            # Validate required fields
            for f in ("shopId", "name", "phone"):
                if f not in body:
                    return _build_response(400, {"success": False, "error": f"Field '{f}' is required"})
                if not isinstance(body[f], str) or not body[f].strip():
                    return _build_response(400, {"success": False, "error": f"Field '{f}' cannot be empty"})

            pref_lang = body.get("preferredLanguage") or body.get("language") or body.get("language_code")
            if pref_lang:
                pref_lang = normalize_language_code(pref_lang)
            try:
                customer = ledger_service.create_customer(
                    shop_id=body["shopId"],
                    name=body["name"],
                    phone=body["phone"],
                    customer_id=body.get("customerId"),
                    preferred_language=pref_lang,
                )
            except TypeError:
                customer = ledger_service.create_customer(
                    shop_id=body["shopId"],
                    name=body["name"],
                    phone=body["phone"],
                    customer_id=body.get("customerId"),
                )
                if pref_lang and hasattr(ledger_service, "update_customer_language"):
                    try:
                        ledger_service.update_customer_language(customer.get("customerId"), pref_lang)
                    except Exception:
                        pass
            return _build_response(201, {"success": True, "customer": customer})

        # ---------------------------------------------------------------------
        # ROUTE: GET /customers
        # ---------------------------------------------------------------------
        if http_method == "GET" and path == "/customers":
            shop_id = query_params.get("shopId")
            if not shop_id or not shop_id.strip():
                return _build_response(400, {"success": False, "error": "Query parameter 'shopId' is required"})

            customers = ledger_service.list_customers(shop_id=shop_id.strip())
            return _build_response(200, {"success": True, "customers": customers, "count": len(customers)})

        # ---------------------------------------------------------------------
        # ROUTE: GET /customers/{customerId}/transactions
        # ---------------------------------------------------------------------
        tx_match = re.match(r"^/customers/([^/]+)/transactions$", path)
        if http_method == "GET" and (tx_match or (path_params.get("customerId") and path.endswith("/transactions"))):
            cid = path_params.get("customerId") or (tx_match.group(1) if tx_match else "")
            if not cid:
                return _build_response(400, {"success": False, "error": "customerId cannot be empty"})

            shop_id = query_params.get("shopId")
            transactions = ledger_service.get_customer_transactions(customer_id=cid, shop_id=shop_id)
            current_balance = ledger_service.calculate_customer_balance(customer_id=cid, shop_id=shop_id)
            return _build_response(
                200,
                {
                    "success": True,
                    "customerId": cid,
                    "balance": int(current_balance) if current_balance % 1 == 0 else float(current_balance),
                    "transactions": transactions,
                    "count": len(transactions),
                },
            )

        # ---------------------------------------------------------------------
        # ROUTE: GET /customers/{customerId}
        # ---------------------------------------------------------------------
        cust_match = re.match(r"^/customers/([^/]+)$", path)
        if http_method == "GET" and (cust_match or path_params.get("customerId")):
            cid = path_params.get("customerId") or (cust_match.group(1) if cust_match else "")
            if not cid:
                return _build_response(400, {"success": False, "error": "customerId cannot be empty"})

            shop_id = query_params.get("shopId")
            customer = ledger_service.get_customer(customer_id=cid, shop_id=shop_id)
            if not customer:
                return _build_response(404, {"success": False, "error": f"Customer '{cid}' not found"})
            return _build_response(200, {"success": True, "customer": customer})

        # ---------------------------------------------------------------------
        # ROUTE: POST /transactions
        # ---------------------------------------------------------------------
        if http_method == "POST" and path == "/transactions":
            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                return _build_response(status_code, body)

            # Validate required fields
            for f in ("shopId", "customerId", "type", "amount"):
                if f not in body:
                    return _build_response(400, {"success": False, "error": f"Field '{f}' is required"})

            for str_f in ("shopId", "customerId", "type"):
                if not isinstance(body[str_f], str) or not body[str_f].strip():
                    return _build_response(400, {"success": False, "error": f"Field '{str_f}' cannot be empty"})

            # Validate transaction type
            tx_type = body["type"].strip().upper()
            if tx_type not in ("CREDIT", "PAYMENT"):
                return _build_response(
                    400,
                    {"success": False, "error": "Transaction type must be CREDIT or PAYMENT"},
                )

            # Validate amount
            try:
                amt = float(body["amount"])
            except (ValueError, TypeError):
                return _build_response(400, {"success": False, "error": "amount must be a numeric value"})

            if amt <= 0:
                return _build_response(400, {"success": False, "error": "amount must be greater than zero"})

            txn_lang = body.get("language") or body.get("language_code") or body.get("detected_language")
            if txn_lang:
                txn_lang = normalize_language_code(txn_lang)
            try:
                transaction = ledger_service.add_transaction(
                    shop_id=body["shopId"],
                    customer_id=body["customerId"],
                    tx_type=tx_type,
                    amount=amt,
                    description=body.get("description", ""),
                    due_date=body.get("dueDate"),
                    transaction_id=body.get("transactionId"),
                    language=txn_lang,
                )
            except TypeError:
                transaction = ledger_service.add_transaction(
                    shop_id=body["shopId"],
                    customer_id=body["customerId"],
                    tx_type=tx_type,
                    amount=amt,
                    description=body.get("description", ""),
                    due_date=body.get("dueDate"),
                    transaction_id=body.get("transactionId"),
                )
            return _build_response(201, {"success": True, "transaction": transaction})

        # ---------------------------------------------------------------------
        # ROUTE: POST /message (or fallback message ingestion)
        # Invokes Amazon Bedrock for transaction entity extraction
        # ---------------------------------------------------------------------
        if http_method == "POST" and (not path or path in ("/", "/message")):
            is_valid, body, status_code = _extract_and_validate_body(event)
            if not is_valid:
                return _build_response(status_code, body)

            if "message" not in body:
                return _build_response(400, {"success": False, "error": "Field 'message' is required"})

            message_val = body["message"]
            if not isinstance(message_val, str):
                return _build_response(400, {"success": False, "error": "Field 'message' must be a string"})

            clean_message = message_val.strip()
            if not clean_message:
                return _build_response(400, {"success": False, "error": "Field 'message' cannot be empty"})

            # Extract structured transaction via Bedrock with language hint (multilingual 23 langs)
            # Accept optional language_code / language from body; if missing, detect from script
            req_lang = body.get("language_code") or body.get("languageCode") or body.get("language") or body.get("lang")
            if req_lang:
                norm_lang = normalize_language_code(req_lang)
                detected_for_resp = norm_lang
            else:
                # Auto-detect from text script for better extraction & response
                detected_for_resp = detect_language_from_text(clean_message)
                norm_lang = detected_for_resp
            extracted_tx = bedrock_service.extract_transaction(clean_message, language_code=norm_lang)

            resp_payload: Dict[str, Any] = {
                "success": True,
                "message": clean_message,
                "status": "received",
                "extractedTransaction": extracted_tx,
                "detected_language": detected_for_resp,
            }
            if req_lang:
                resp_payload["requested_language"] = req_lang
            # Also include transcript_language for consistency with WhatsApp
            resp_payload["language"] = detected_for_resp
            return _build_response(200, resp_payload)

        # ---------------------------------------------------------------------
        # Non-matching HTTP methods / routes
        # ---------------------------------------------------------------------
        if http_method not in ("GET", "POST"):
            return _build_response(
                405,
                {"success": False, "error": f"Method {http_method} not allowed."},
            )

        return _build_response(
            404,
            {"success": False, "error": f"Route not found: {http_method} {path}"},
        )

    except LedgerValidationError as e:
        return _build_response(400, {"success": False, "error": str(e)})

    except BedrockExtractionError as e:
        return _build_response(400, {"success": False, "error": f"Transaction extraction failed: {str(e)}"})

    except BedrockUnavailableError as e:
        return _build_response(
            503,
            {
                "success": False,
                "error": "Amazon Bedrock service is unavailable or not configured. Ensure AWS credentials and model access are configured.",
                "details": str(e),
            },
        )

    except TranscribeUnavailableError as e:
        return _build_response(
            503,
            {
                "success": False,
                "error": "AWS Transcribe service is unavailable or not configured. Ensure TRANSCRIBE_S3_BUCKET and AWS credentials are configured. For whisper-only langs, set WHISPER_ENDPOINT_URL.",
                "details": str(e),
            },
        )

    except (WhisperUnavailableError, WhisperTranscriptionFailedError) as e:
        is_unavail = isinstance(e, WhisperUnavailableError)
        return _build_response(
            503 if is_unavail else 400,
            {
                "success": False,
                "error": f"Whisper {'unavailable' if is_unavail else 'transcription failed'}: {str(e)}",
                "details": str(e),
            },
        )

    except TranscriptionFailedError as e:
        return _build_response(400, {"success": False, "error": f"Transcription failed: {str(e)}"})

    except WhatsAppUnavailableError as e:
        return _build_response(
            503,
            {
                "success": False,
                "error": "WhatsApp Graph API is unavailable or not configured. Ensure WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID are configured.",
                "details": str(e),
            },
        )

    except WhatsAppValidationError as e:
        return _build_response(400, {"success": False, "error": str(e)})

    except DynamoDBUnavailableError as e:
        return _build_response(
            503,
            {
                "success": False,
                "error": "DynamoDB service is unavailable or not configured. Ensure AWS credentials, tables (CUSTOMERS_TABLE, TRANSACTIONS_TABLE), or DYNAMODB_ENDPOINT_URL are configured.",
                "details": str(e),
            },
        )

    except Exception as e:
        return _build_response(
            500,
            {"success": False, "error": "Internal server error", "details": str(e)},
        )
