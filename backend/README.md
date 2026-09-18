# Ledgerly - Backend Services & AWS Architecture

This directory houses the backend logic and serverless infrastructure for **Ledgerly** — WhatsApp voice/text → Transcribe → Bedrock → deterministic DynamoDB ledger.

---

## Directory Layout
```text
backend/
├── lambda/
│   ├── handler.py                   # AWS Lambda entrypoint (API Gateway router, WhatsApp webhook, validators)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ledger_service.py        # DynamoDB data layer & deterministic balance math
│   │   ├── bedrock_service.py       # Bedrock extraction + WhatsApp reply generation
│   │   ├── transcribe_service.py    # AWS Transcribe STT (S3 + polling)
│   │   └── whatsapp_service.py      # Meta Graph API (verify/parse/media/send)
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_backend.py          # Offline unittest suite (no AWS/network required)
│   └── README.md                    # Lambda API specifications & contract details
├── requirements.txt                 # boto3, botocore, requests
└── README.md                        # Architecture overview & testing guide
```

---

## Architecture Flow

```
WhatsApp (text / voice note: audio/ogg)
       │  Meta Graph API v18.0 webhook
       ▼
Amazon API Gateway
  ├─ GET  /whatsapp/webhook        → verify hub.challenge
  ├─ POST /whatsapp/webhook        → text|voice ingestion
  ├─ POST /whatsapp/transcribe     → direct STT (s3_uri / audio_base64)
  ├─ POST /message                 → text → Bedrock extraction (no DB write)
  ├─ POST /customers, GET /customers, GET /customers/{id}
  └─ POST /transactions, GET /customers/{id}/transactions
       │ (Lambda Proxy Integration)
       ▼
AWS Lambda (backend/lambda/handler.py)
       │
       ├──> WhatsAppService (whatsapp_service.py)
       │      verify_webhook / parse_webhook / download_media / send_text / resolve_shop_id
       │
       ├──> TranscribeService (transcribe_service.py)  [voice only]
       │      S3 PUT whatsapp/{uuid}.ogg → start_transcription_job → poll → fetch TranscriptFileUri → S3 DELETE
       │      supports ogg/mp3/mp4/wav, 10 MB cap, TRANSCRIBE_LANGUAGE=en-IN|auto
       │
       ├──> BedrockService (bedrock_service.py)
       │      extract_transaction: customerName, type CREDIT|PAYMENT, amount, description  (temp 0.0, strict JSON)
       │      generate_reply: Hinglish WhatsApp confirmation from extracted + deterministic balance (temp 0.3, fallback template)
       │
       └──> LedgerService (ledger_service.py) → DynamoDB
              ├── Customers Table (customerId PK, shopId GSI) — put/get/scan
              └── Transactions Table (transactionId PK, customerId GSI) — put/scan
                     balance = SUM(CREDIT) - SUM(PAYMENT)  (Decimal, _to_serializable)
```

**Sync ack:** `POST /whatsapp/webhook` always returns `200` to Meta (prevents retries) even on `400` extraction/transcription failures; error also sent as WhatsApp text if `WHATSAPP_TOKEN` configured. Direct API callers receive `400/503` via `_extract_and_validate_body` and service exceptions.

---

## Service Details

### WhatsAppService (`services/whatsapp_service.py`)
* `GRAPH_BASE = https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}` (default `v18.0`)
* `verify_webhook`: `hub.mode=subscribe`, `hub.verify_token` vs `WHATSAPP_VERIFY_TOKEN`, returns `hub.challenge` plain text
* `verify_signature`: HMAC SHA256 `X-Hub-Signature-256` if `WHATSAPP_APP_SECRET` set
* `parse_webhook`: `entry[].changes[].value.messages[]` → `{from, phone_number_id, message_id, type, text/audio_id, mime_type}`
* `download_media(mediaId)`: `GET /{mediaId}` → `{url}` → `GET {url}` (Bearer token), 10 MB cap
* `send_text(to, text)`: `POST /{phone_number_id}/messages` `{messaging_product: whatsapp, type: text}`
* `resolve_shop_id(phone_number_id)`: `SHOP_PHONE_MAP` JSON else `DEFAULT_SHOP_ID`

### TranscribeService (`services/transcribe_service.py`)
* `_get_transcribe_client` / `_get_s3_client` (injected for tests)
* `_upload_to_s3`: `TRANSCRIBE_S3_BUCKET` required else `TranscribeUnavailableError`
* `_poll_job`: `get_transcription_job` every 1s until `COMPLETED`/`FAILED` or `30s` timeout → `TranscriptFileUri`
* `_fetch_transcript_text`: `urllib` fetch `results.transcripts[0].transcript`
* `transcribe_s3_uri(s3_uri, language_code, media_format)` + `transcribe_audio_bytes(bytes, media_format)` (enforces `MAX_VOICE_BYTES`)

### BedrockService (`services/bedrock_service.py`)
* `EXTRACTION_SYSTEM_PROMPT`: strict JSON `{customerName, type, amount, description}`, forbids balance
* `REPLY_SYSTEM_PROMPT`: 1-2 line Hinglish WhatsApp reply with `₹`, never recalculates balance
* Supports Claude (`anthropic_version`), Titan (`inputText`), Llama/Nova fallback
* `generate_reply` falls back to deterministic template on `BedrockUnavailableError` → `Rahul ke khate me ₹500 udhar joda. Kul udhar: ₹1200. ✅`

### LedgerService (`services/ledger_service.py`)
* `_to_decimal(Decimal(str(val)))`, `_to_serializable(Decimal→int/float)`
* Tables via `CUSTOMERS_TABLE`/`TRANSACTIONS_TABLE` env, `DYNAMODB_ENDPOINT_URL` for local
* `create_customer` (unconditional `put_item`), `get_customer` (shopId check), `list_customers` (Scan+Attr), `get_customer_transactions` (Scan+sort reverse `createdAt`), `calculate_customer_balance`, `add_transaction` (put → recalculate → `update_item SET balance` swallowed `except pass`)

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `WHATSAPP_TOKEN` | *(none)* | Meta Graph API Bearer token (system user) |
| `WHATSAPP_PHONE_NUMBER_ID` | *(none)* | Graph API phone number ID for sending |
| `WHATSAPP_VERIFY_TOKEN` | *(none)* | Webhook verification token (must match Meta dashboard) |
| `WHATSAPP_APP_SECRET` | *(none)* | Optional HMAC `X-Hub-Signature-256` verification |
| `WHATSAPP_GRAPH_VERSION` | `v18.0` | Graph API version |
| `DEFAULT_SHOP_ID` | `shop001` | Fallback `shopId` when `SHOP_PHONE_MAP` miss |
| `SHOP_PHONE_MAP` | *(none)* | JSON map `{"phone_number_id":"shopId"}` |
| `TRANSCRIBE_S3_BUCKET` | *(none)* | S3 bucket for transient voice audio (required for voice) |
| `TRANSCRIBE_LANGUAGE` | `en-IN` | `en-IN`, `hi-IN`, or `auto` |
| `MAX_VOICE_BYTES` | `10485760` | Max voice note size (10 MB) |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` | Bedrock model for extraction + generation |
| `AWS_REGION` | `us-east-1` | Region for Bedrock/DynamoDB/Transcribe/S3 |
| `CUSTOMERS_TABLE` | `Customers` | DynamoDB Customers table |
| `TRANSACTIONS_TABLE` | `Transactions` | DynamoDB Transactions table |
| `DYNAMODB_ENDPOINT_URL` | *(none)* | Local DynamoDB `http://localhost:8000` |

### Financial Rule:
> [!IMPORTANT]
> Bedrock is ONLY for extraction/generation. Balance arithmetic (`balance = SUM CREDIT - SUM PAYMENT`) is deterministic backend code, **never** LLM.

---

## Deployment Checklist

1. **DynamoDB:** `Customers` (PK `customerId` String) + `Transactions` (PK `transactionId` String); on-demand; GSI `shopId`/`customerId` planned (currently Scan)
2. **S3:** `TRANSCRIBE_S3_BUCKET` with lifecycle delete 1d
3. **Lambda:** `handler.lambda_handler`, Python 3.11, timeout **60s**, memory 512MB, env from table above
4. **API Gateway HTTP API:** routes `GET /whatsapp/webhook`, `POST /whatsapp/webhook`, `POST /whatsapp/transcribe`, `POST /message`, `POST/GET /customers*`, `POST /transactions`; CORS `GET,POST,OPTIONS`
5. **IAM:** `dynamodb:GetItem/PutItem/UpdateItem/Scan/Query`, `s3:PutObject/GetObject/DeleteObject`, `transcribe:StartTranscriptionJob/GetTranscriptionJob/DeleteTranscriptionJob`, `bedrock:InvokeModel`, `logs:*`
6. **Bedrock:** enable `anthropic.claude-3-haiku-20240307-v1:0` in `AWS_REGION`
7. **Meta:** App → WABA → webhook `https://<apigw>/whatsapp/webhook` with `WHATSAPP_VERIFY_TOKEN`, subscribe `messages`

---

## Running the Unit Test Suite

Offline, no AWS creds, mocked boto3:

```bash
python3 -m unittest backend/lambda/tests/test_backend.py -v
# or
python3 -m unittest discover -s backend/lambda/tests -v
```

### Test Coverage (17 Tests):
- **Bedrock Extraction**:
  - `Rahul took rice for 500 on credit` → `CREDIT / 500 / Rahul / rice`
  - `Rahul paid 300` → `PAYMENT / 300 / Rahul / ""`
  - Non-JSON / empty / unsupported type / non-positive / non-numeric amount / missing customerName → `BedrockExtractionError`
- **Bedrock Reply** (via `generate_reply` fallback template tested manually):
  - `CREDIT` → `Rahul ke khate me ₹500 udhar joda. Kul udhar: ₹1200. ✅`
  - `PAYMENT` → `Rahul ne ₹300 jama kiye. Bacha udhar: ₹900. 🙏`
- **TranscribeService** (mocked clients):
  - Empty `s3_uri`/bytes, oversized audio, S3 missing bucket → `TranscriptionFailedError`/`TranscribeUnavailableError`
- **WhatsAppService** (mocked Graph):
  - `verify_webhook` success/fail, `parse_webhook` text/audio/unsupported/status, `download_media`/`send_text` mocked
- **Lambda Handler**:
  - `GET /whatsapp/webhook` verify 200/403
  - `POST /whatsapp/webhook` text→ledger, voice→STT→ledger, status update ack, unsupported type skip, transcription/extraction failure branches (always 200 for Meta)
  - `POST /whatsapp/transcribe` s3_uri/audio_base64
  - `POST /message` valid/503/400, missing/empty message, customer/transaction validation → `400`
- **Deterministic Ledger**:
  - `balance = SUM CREDIT - SUM PAYMENT` (`500+250-300=450`)

---

## API Contract

See `docs/api-contract.md` for full HTTP examples and error codes, and `backend/lambda/README.md` for per-route specs.
