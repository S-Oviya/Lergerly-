# Ledgerly

Ledgerly is an AI-powered digital ledger designed to help local shopkeepers manage customer credit, payments, and outstanding balances via WhatsApp voice notes and text.

My contribution focuses on the **backend ledger, transaction API, and WhatsApp voice pipeline** — storing customers, recording transactions, calculating balances deterministically, and processing WhatsApp voice notes through Speech-to-Text and LLM extraction.

## What I Worked On

### Backend API & WhatsApp Voice Pipeline

Implemented a Python-based backend with a Lambda-compatible handler covering:

* Customer creation / retrieval / listing
* Transaction creation / history / balance
* Natural-language message ingestion (`POST /message`)
* **WhatsApp Cloud API webhook** (`GET /whatsapp/webhook` verification + `POST /whatsapp/webhook` ingestion)
* **Voice note pipeline:** WhatsApp audio → `download_media` → AWS Transcribe → Bedrock extraction → deterministic ledger → WhatsApp reply
* Direct transcribe helper (`POST /whatsapp/transcribe`) for testing with `s3_uri` or `audio_base64`
* Request validation, HMAC signature verification, error handling, CORS

### AI Layer — Strict Separation

* **Amazon Bedrock** (`services/bedrock_service.py`) is used ONLY for:
  * Entity extraction: `customerName`, `type` (CREDIT/PAYMENT), `amount`, `description` from text/transcript
  * Reply generation: concise WhatsApp confirmation (Hinglish) from extracted transaction + deterministic balance
* **AWS Transcribe** (`services/transcribe_service.py`) converts WhatsApp `audio/ogg` (and mp3/mp4/wav) to text via S3 transient upload + polling.
* **Financial arithmetic is NEVER done by the LLM.** Balance is computed deterministically in `services/ledger_service.py`:

```text
Balance = SUM(CREDIT) - SUM(PAYMENT)
```

Implemented with `Decimal(str(amount))` for precision and `_to_serializable` for JSON.

### WhatsApp Service

`services/whatsapp_service.py` handles Meta Graph API (`v18.0`):

* `verify_webhook()` — `hub.mode=subscribe` + `hub.verify_token` + `hub.challenge`
* `parse_webhook()` — normalizes `entry[].changes[].value.messages[]` into `{from, phone_number_id, message_id, type, text/audio_id}`
* `download_media(mediaId)` — `GET /{mediaId}` → `{url}` → `GET {url}` with `Bearer WHATSAPP_TOKEN`
* `send_text(to, text)` — `POST /{phone_number_id}/messages`
* `resolve_shop_id(phone_number_id)` — via `SHOP_PHONE_MAP` JSON or `DEFAULT_SHOP_ID`

### Ledger Logic

`services/ledger_service.py` (DynamoDB-compatible, boto3):

* Tables: `Customers` (`customerId` PK, `shopId` GSI) and `Transactions` (`transactionId` PK, `customerId` GSI)
* `create_customer`, `get_customer`, `list_customers` (Scan+Attr filter), `get_customer_transactions`, `calculate_customer_balance`, `add_transaction` (put + recalculate + `update_item SET balance`)
* Deterministic balance verified by unit test: `500 + 250 - 300 = 450`

### API Integration

Frontend API service:

```text
src/services/api.ts
```

Provides `sendMessage()`, `createCustomer()`, `createTransaction()` against `VITE_API_BASE_URL`. WhatsApp flow bypasses the frontend — it hits the backend directly via the Meta webhook.

### Validation & Testing

Validation covers:

* Missing / empty bodies, invalid JSON, base64
* Missing `message`, empty `message`
* Invalid `shopId`/`name`/`phone`, `customerId`
* Invalid `type` (must be `CREDIT`|`PAYMENT`), `amount <= 0` or non-numeric
* Empty Transcribe result, oversized audio (>10 MB), unsupported message types
* `WHATSAPP_VERIFY_TOKEN` mismatch, `X-Hub-Signature-256` HMAC
* Unconfigured DynamoDB / Bedrock / Transcribe / WhatsApp → `503` with `details`

Backend tests (offline, mocked boto3, no AWS creds needed):

```text
17/17 tests passing (ledger + Bedrock + handler)
+ manual webhook integration tests (text + voice + status updates + failure branches)
```

## Backend Structure

```text
backend/
├── lambda/
│   ├── handler.py                          # API Gateway router + WhatsApp webhook
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ledger_service.py               # DynamoDB + deterministic balance
│   │   ├── bedrock_service.py              # Bedrock extraction + reply generation
│   │   ├── transcribe_service.py           # AWS Transcribe (S3 + polling)
│   │   └── whatsapp_service.py             # Meta Graph API (verify/parse/media/send)
│   └── tests/
│       ├── __init__.py
│       └── test_backend.py                 # 17 unit tests (offline)
├── requirements.txt                        # boto3, botocore, requests
└── README.md
```

## Data Model

### Customer

```text
customerId
shopId
name
phone
balance       # Decimal, updated deterministically
createdAt     # ISO-8601 UTC
```

### Transaction

```text
transactionId
shopId
customerId
type          # CREDIT | PAYMENT
amount        # Decimal
description
dueDate       # optional
createdAt
updatedCustomerBalance  # returned on POST /transactions and WhatsApp flow
```

## API Endpoints

### `POST /whatsapp/webhook` — WhatsApp Inbound (Text & Voice)

Meta webhook payload. Handles `text` and `audio`/`voice` (`audio/ogg`).

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "changes": [{
      "value": {
        "metadata": {"phone_number_id": "111"},
        "messages": [{
          "from": "919876543210",
          "id": "wamid.xxx",
          "type": "voice",
          "voice": {"id": "media_123", "mime_type": "audio/ogg"}
        }]
      }
    }]
  }]
}
```

Flow: `download_media` → Transcribe → Bedrock `extract_transaction` → `findOrCreateCustomer` → `add_transaction` → Bedrock `generate_reply` → `send_text`. Returns `200 {success, count, results[]}` (WhatsApp requires 200 to stop retries). Verification via `GET /whatsapp/webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...`.

### `POST /whatsapp/transcribe` — Direct STT (testing)

```json
{"s3_uri": "s3://bucket/key.ogg"}
{"audio_base64": "<base64 ogg>"}
```

### `POST /message`

Natural-language text → Bedrock extraction (no ledger write).

```json
{"message": "Rahul took rice for 500 on credit"}
```

### `POST /customers` / `GET /customers?shopId=` / `GET /customers/{id}` / `POST /transactions` / `GET /customers/{id}/transactions`

See `docs/api-contract.md`.

## Architecture of My Part

```text
WhatsApp (text / voice note)
    │
    │  webhook (Graph API v18)
    ▼
API Gateway ( /whatsapp/webhook , /message , /customers , /transactions )
    │
    ▼
Lambda handler.py
    ├── GET /whatsapp/webhook ──► verify_webhook (challenge)
    │
    ├── POST /whatsapp/webhook ──► whatsapp_service.parse ──► [audio?] ──► whatsapp_service.download_media
    │                                    │                       │
    │                                    │                       ▼
    │                                    │               transcribe_service.transcribe_audio_bytes
    │                                    │                       │ (S3 PUT → Transcribe start → poll → fetch transcript → S3 DELETE)
    │                                    │                       ▼
    │                                    └──► bedrock_service.extract_transaction ──► findOrCreateCustomer ──► ledger_service.add_transaction
    │                                                                                │ (calculate_customer_balance: SUM CREDIT - SUM PAYMENT)
    │                                                                                ▼
    │                                                                    bedrock_service.generate_reply ──► whatsapp_service.send_text
    │
    ├── POST /whatsapp/transcribe ──► transcribe_service.transcribe_s3_uri / transcribe_audio_bytes
    ├── POST /message ──► bedrock_service.extract_transaction (no DB write)
    └── Ledger routes ──► ledger_service (DynamoDB)
                                │
                                ▼
                         Customers / Transactions
                                │
                                ▼
                         Deterministic Balance
```

LLM is isolated to extraction/generation; all financial math is deterministic. WhatsApp flow always acks `200` to prevent Meta retries, even on `400` extraction errors (error also sent as WhatsApp text if token configured).

## Environment Variables

```env
# WhatsApp Cloud API (Meta)
WHATSAPP_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=ledgerly_verify_2026
WHATSAPP_APP_SECRET=            # optional HMAC
WHATSAPP_GRAPH_VERSION=v18.0
DEFAULT_SHOP_ID=shop001
SHOP_PHONE_MAP={"YOUR_PHONE_NUMBER_ID":"shop001"}

# Voice Transcription
TRANSCRIBE_S3_BUCKET=ledgerly-whatsapp-audio
TRANSCRIBE_LANGUAGE=en-IN       # or auto for hi-IN detection
MAX_VOICE_BYTES=10485760

# AWS / Bedrock / DynamoDB
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
CUSTOMERS_TABLE=Customers
TRANSACTIONS_TABLE=Transactions
DYNAMODB_ENDPOINT_URL=          # optional local http://localhost:8000
VITE_API_BASE_URL=              # frontend API Gateway URL
```

## Testing

```bash
python3 -m unittest backend/lambda/tests/test_backend.py -v
npm run build
```

## Frontend API Layer

`src/services/api.ts` keeps HTTP separate from UI; `VITE_API_BASE_URL` points to API Gateway. WhatsApp bypasses this layer — Meta calls the backend directly.

## Deployment Notes

1. Create DynamoDB `Customers` (`customerId` PK) and `Transactions` (`transactionId` PK) + S3 bucket `TRANSCRIBE_S3_BUCKET`
2. Lambda `handler.lambda_handler`, timeout 60s, memory 512MB, IAM: `dynamodb:*`, `s3:Put/Get/Delete`, `transcribe:*`, `bedrock:InvokeModel`, `logs:*`
3. API Gateway HTTP API with routes above; enable `GET,POST,OPTIONS`
4. Enable Bedrock model access in `AWS_REGION`
5. Meta App → WABA → configure webhook `https://<apigw>/whatsapp/webhook` with `WHATSAPP_VERIFY_TOKEN`, subscribe to `messages`
