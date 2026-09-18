# Ledgerly API Contract (Current Lambda Backend)

This document specifies the exact HTTP API contract implemented in `backend/lambda/handler.py` (services: `ledger_service.py`, `bedrock_service.py`, `transcribe_service.py`, `whatsapp_service.py`).

All JSON responses include `Access-Control-Allow-Origin: *` (except `GET /whatsapp/webhook` verification which returns `text/plain` challenge). `POST /whatsapp/webhook` always acks `200` to Meta to prevent retries.

---

## 1. `GET /whatsapp/webhook` — Webhook Verification

### Purpose
Meta Graph API verifies the webhook during setup (`hub.mode=subscribe`).

### Query Parameters
| Field | Type | Required | Description |
|---|---|---|---|
| `hub.mode` | string | **Yes** | Must be `subscribe` |
| `hub.verify_token` | string | **Yes** | Must equal `WHATSAPP_VERIFY_TOKEN` env |
| `hub.challenge` | string | **Yes** | Random string Meta expects back verbatim |

Supports both `queryStringParameters` and `rawQueryString` (API Gateway v1/v2).

### Example Request
```http
GET /whatsapp/webhook?hub.mode=subscribe&hub.verify_token=ledgerly_verify_2026&hub.challenge=CHALL_123
```

### Successful Response (`200 OK`, `Content-Type: text/plain`)
```
CHALL_123
```

### Error Responses
- `403 Forbidden` `{"success":false,"error":"Verify token mismatch"}`
- `403` `{"success":false,"error":"WHATSAPP_VERIFY_TOKEN is not configured on server"}`

---

## 2. `POST /whatsapp/webhook` — WhatsApp Inbound (Text & Voice → STT → Bedrock → Ledger → Reply)

### Purpose
Single entry for shopkeeper WhatsApp messages (text and voice notes). Executes: `download_media` (if audio) → Transcribe → Bedrock extraction → `findOrCreateCustomer` → `add_transaction` → Bedrock `generate_reply` → `send_text` (WhatsApp). Always returns `200` to ack Meta.

### Headers (optional)
| Header | Required | Description |
|---|---|---|
| `X-Hub-Signature-256` | No | `sha256=<hmac>` verified against `WHATSAPP_APP_SECRET` if set |

### Request JSON (Meta shape)
| Field | Type | Description |
|---|---|---|
| `object` | string | `whatsapp_business_account` |
| `entry[].changes[].value.metadata.phone_number_id` | string | WABA phone number ID → resolves `shopId` via `SHOP_PHONE_MAP`/`DEFAULT_SHOP_ID` |
| `entry[].changes[].value.messages[]` | array | Each: `{from, id (wamid), type, timestamp, text|audio/voice}` |
| `type=text` → `text.body` | string | Text body |
| `type=audio|voice` → `audio.id` / `voice.id`, `mime_type` | string | Media ID → Graph `GET /{id}` → `audio/ogg` bytes; supports `ogg`/`mp3`/`mp4`/`wav` |

### Example Request — Text
```http
POST /whatsapp/webhook
Content-Type: application/json

{
  "object": "whatsapp_business_account",
  "entry": [{
    "changes": [{
      "value": {
        "metadata": {"phone_number_id": "111"},
        "messages": [{
          "from": "919876543210",
          "id": "wamid.text1",
          "timestamp": "1710000000",
          "type": "text",
          "text": {"body": "Rahul took rice for 500 on credit"}
        }]
      }
    }]
  }]
}
```

### Example Request — Voice Note
```http
POST /whatsapp/webhook
Content-Type: application/json

{
  "object": "whatsapp_business_account",
  "entry": [{
    "changes": [{
      "value": {
        "metadata": {"phone_number_id": "111"},
        "messages": [{
          "from": "919876543210",
          "id": "wamid.voice1",
          "timestamp": "1710000000",
          "type": "voice",
          "voice": {"id": "media_123", "mime_type": "audio/ogg"}
        }]
      }
    }]
  }]
}
```

### Successful Response (`200 OK`) — Always ack
```json
{
  "success": true,
  "status": "processed",
  "count": 1,
  "results": [
    {
      "message_id": "wamid.voice1",
      "status": "processed",
      "from": "919876543210",
      "shopId": "shop001",
      "type": "voice",
      "transcript": "Rahul paid 300",
      "extractedTransaction": {
        "customerName": "Rahul",
        "type": "PAYMENT",
        "amount": 300,
        "description": ""
      },
      "customer": {"customerId": "cust_abc123", "name": "Rahul"},
      "transaction": {
        "transactionId": "tx_xyz789",
        "shopId": "shop001",
        "customerId": "cust_abc123",
        "type": "PAYMENT",
        "amount": 300,
        "description": "",
        "createdAt": "2026-09-17T14:20:00+00:00",
        "updatedCustomerBalance": 200
      },
      "balance": 200,
      "reply": "Rahul ne ₹300 jama kiye. Bacha udhar: ₹200. 🙏",
      "whatsapp_send": "sent",
      "transcription_meta": {"audio_bytes_len": 12345, "transcript": "Rahul paid 300"}
    }
  ]
}
```

Per-message `status` values:
- `processed` — full pipeline succeeded (includes `whatsapp_send: sent|skipped_no_token|failed: ...`)
- `skipped` — unsupported `type` (e.g. `image`) → `{"error":"Unsupported message type 'image'"}`
- `failed` — `TranscriptionFailedError` (empty/silent/oversize) or `BedrockExtractionError` (invalid JSON/type/amount) — WhatsApp error text also sent if `WHATSAPP_TOKEN` set
- `error` + `code:503` — Buddy `TranscribeUnavailableError` / `WhatsAppUnavailableError` / `DynamoDBUnavailableError` / `BedrockUnavailableError`

Status updates (Meta `statuses` without `messages`) → `200 {"success":true,"status":"received","processed":0,"reason":"No messages..."}`

### Validation & Error Responses
- `403` `{"success":false,"error":"Invalid X-Hub-Signature-256"}` (HMAC mismatch)
- `403` `{"success":false,"error":"Verify token mismatch"}` (GET verify)
- `400` transcription `{"success":false,"error":"Transcription failed: ..."}`
- `400` extraction `{"success":false,"error":"Transaction extraction failed: ..."}`
- `503` `{"success":false,"error":"AWS Transcribe service is unavailable...","details":"..."}` / `WhatsApp Graph API is unavailable...` / `Amazon Bedrock service is unavailable...` / `DynamoDB service is unavailable...` — but `POST /whatsapp/webhook` still `200` with `results[].code=503` to ack Meta

---

## 3. `POST /whatsapp/transcribe` — Direct STT (Testing)

### Purpose
Transcribe audio without WhatsApp (for local testing). Supports `s3_uri` or `audio_base64`.

### Request JSON
| Field | Type | Required | Description |
|---|---|---|---|
| `s3_uri` | string | One of | `s3://bucket/key.ogg` (`ogg`/`mp3`/`mp4`/`wav`) |
| `audio_base64` | string | One of | Base64-encoded audio bytes |
| `media_format` | string | No | `ogg` (default), `mp3`, `mp4`, `wav` |
| `language_code` | string | No | `en-IN` (default from `TRANSCRIBE_LANGUAGE`), `hi-IN`, `auto` |

### Example Request
```http
POST /whatsapp/transcribe
Content-Type: application/json

{"s3_uri": "s3://ledgerly-whatsapp-audio/whatsapp/test.ogg"}
```
```http
POST /whatsapp/transcribe
Content-Type: application/json

{"audio_base64": "<base64>", "media_format": "ogg", "language_code": "auto"}
```

### Successful Response (`200 OK`)
```json
{"success": true, "transcript": "Rahul took rice for 500 on credit"}
```

### Error Responses
- `400` `{"success":false,"error":"Provide either 's3_uri' or 'audio_base64'"}`
- `400` `{"success":false,"error":"Transcription failed: ... (empty/too large/timeout)"}`
- `503` `{"success":false,"error":"AWS Transcribe service is unavailable...","details":"..."}`

---

## 4. `POST /message` (Natural-Language Ingestion)

### Purpose
Text-only ingestion for frontend or direct testing. Passes text to Bedrock extraction (no DB write). For WhatsApp text, prefer `POST /whatsapp/webhook`.

### Request JSON
| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | **Yes** | Natural language note. Must not be empty. |

### Example Request
```http
POST /message
Content-Type: application/json

{"message": "Rahul took rice for 500 on credit"}
```

### Successful Response (`200 OK`)
```json
{
  "success": true,
  "message": "Rahul took rice for 500 on credit",
  "status": "received",
  "extractedTransaction": {
    "customerName": "Rahul",
    "type": "CREDIT",
    "amount": 500,
    "description": "rice"
  }
}
```

### Validation & Error Responses
- `400` `{"success":false,"error":"Missing request body"}` / `Invalid JSON format` / `Request body must be a JSON object`
- `400` `{"success":false,"error":"Field 'message' is required"}` / `Field 'message' cannot be empty`
- `400` `{"success":false,"error":"Transaction extraction failed: <reason>"}`
- `503` `{"success":false,"error":"Amazon Bedrock service is unavailable...","details":"..."}`

---

## 5. `POST /customers` (Create Customer)

### Required Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `shopId` | string | **Yes** | Store ID (resolved via `SHOP_PHONE_MAP` for WhatsApp) |
| `name` | string | **Yes** | Customer full name |
| `phone` | string | **Yes** | Contact phone; WhatsApp flow uses `from` if not found |
| `customerId` | string | No | Optional custom ID; auto `cust_...` if omitted |

### Example Request
```http
POST /customers
Content-Type: application/json

{"shopId": "shop001", "name": "Rahul Sharma", "phone": "+91 98765 43210"}
```

### Successful Response (`201 Created`)
```json
{
  "success": true,
  "customer": {
    "customerId": "cust_9e7f6a2b1c0d",
    "shopId": "shop001",
    "name": "Rahul Sharma",
    "phone": "+91 98765 43210",
    "balance": 0,
    "createdAt": "2026-09-17T14:30:00.000000+00:00"
  }
}
```

### Errors
- `400` `{"success":false,"error":"Field '<name>' is required"}` / `cannot be empty`
- `503` `{"success":false,"error":"DynamoDB service is unavailable...","details":"..."}`

---

## 6. `POST /transactions` (Record Transaction)

### Required Fields & Allowed Types
| Field | Type | Required | Constraints |
|---|---|---|---|
| `shopId` | string | **Yes** | Must not be empty |
| `customerId` | string | **Yes** | Must not be empty |
| `type` | string | **Yes** | `CREDIT` (udhar, +balance) or `PAYMENT` (jama, -balance) |
| `amount` | number | **Yes** | `> 0` |
| `description` | string | No | Goods note |
| `dueDate` | string | No | Promise date `2026-09-20` |
| `transactionId` | string | No | Auto `tx_...` if omitted |

### Example Request — CREDIT
```http
POST /transactions
Content-Type: application/json

{"shopId":"shop001","customerId":"cust_9e7f6a2b1c0d","type":"CREDIT","amount":500,"description":"2 packets of basmati rice","dueDate":"2026-09-20"}
```

### Example Request — PAYMENT
```http
POST /transactions
Content-Type: application/json

{"shopId":"shop001","customerId":"cust_9e7f6a2b1c0d","type":"PAYMENT","amount":300,"description":"Partial cash payment"}
```

### Successful Response (`201 Created`)
```json
{
  "success": true,
  "transaction": {
    "transactionId": "tx_4a5b6c7d8e9f",
    "shopId": "shop001",
    "customerId": "cust_9e7f6a2b1c0d",
    "type": "CREDIT",
    "amount": 500,
    "description": "2 packets of basmati rice",
    "dueDate": "2026-09-20",
    "createdAt": "2026-09-17T14:35:00.000000+00:00",
    "updatedCustomerBalance": 500
  }
}
```

### Errors
- `400` `Field '<name>' is required` / `cannot be empty`
- `400` `Transaction type must be CREDIT or PAYMENT`
- `400` `amount must be greater than zero` / `amount must be a numeric value`
- `503` `DynamoDB service is unavailable...`

---

## 7. `GET /customers`, `GET /customers/{customerId}`, `GET /customers/{customerId}/transactions`

| Route | Query | Success | Errors |
|---|---|---|---|
| `GET /customers?shopId=shop001` | `shopId` required | `200 {"success":true,"customers":[...],"count":n}` | `400 shopId required`, `503 DynamoDB` |
| `GET /customers/{customerId}?shopId=optional` | optional `shopId` filter | `200 {"success":true,"customer":{...}}` | `404 Customer '...' not found` |
| `GET /customers/{customerId}/transactions?shopId=optional` | optional `shopId` | `200 {"success":true,"customerId":"...","balance":500,"transactions":[...],"count":n}` (sorted reverse `createdAt`) | `400 customerId cannot be empty` |

---

## 8. Deterministic Financial Rule

$$\text{Customer Balance} = \sum \text{CREDIT} - \sum \text{PAYMENT}$$

- **Bedrock extracts**, `ledger_service.calculate_customer_balance` computes via `Decimal`.
- **Reply generation** uses the deterministic `updatedCustomerBalance` (fallback template if Bedrock generation 503).

---

## 9. CORS & Common Errors

All routes return `Access-Control-Allow-Origin: *`, `Allow-Headers: Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token`, `Allow-Methods: GET,POST,OPTIONS`. `OPTIONS *` → `200 {"success":true,"status":"preflight_ok"}`.

| Status | When |
|---|---|
| `400` | Validation (empty/invalid JSON/type/amount, transcription silent) |
| `403` | Webhook verify/signature mismatch |
| `404` | Route not found / customer not found |
| `405` | Method not `GET,POST` |
| `503` | Bedrock / Transcribe / WhatsApp / DynamoDB unconfigured (`details` included) |
| `500` | Internal error (`details` included) |

---

## 10. Frontend Integration Notes

* `VITE_API_BASE_URL` points to API Gateway.
* `shopId` is fixed `shop001` or resolved via `SHOP_PHONE_MAP` for WhatsApp.
* Text bar → `POST /message`; WhatsApp voice → Meta → `POST /whatsapp/webhook` (bypasses frontend).
* `POST /transactions` returns `updatedCustomerBalance` for optimistic UI.

---

## 11. Environment Variables Reference

See `.env.example` and `backend/README.md` table for `WHATSAPP_*`, `TRANSCRIBE_*`, `AWS_REGION`, `BEDROCK_MODEL_ID`, `CUSTOMERS_TABLE`, `TRANSACTIONS_TABLE`.

