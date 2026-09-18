# Ledgerly - AWS Lambda Transaction & Data Layer Handler

## Overview
This Lambda (`handler.py`) + services (`services/ledger_service.py`, `bedrock_service.py`, `transcribe_service.py`, `whatsapp_service.py`) form the serverless backend for **Ledgerly** — WhatsApp text/voice → STT → Bedrock → deterministic ledger.

It handles:
1. **WhatsApp webhook** — verification and text/voice ingestion (`GET/POST /whatsapp/webhook`)
2. **Direct STT** — `POST /whatsapp/transcribe` (s3_uri / audio_base64)
3. **Natural-language ingestion** — `POST /message` (text → Bedrock extraction, no DB write)
4. **Customer accounts** — `POST /customers`, `GET /customers`, `GET /customers/{customerId}`
5. **Transactions & balance** — `POST /transactions`, `GET /customers/{customerId}/transactions`

All JSON responses include `Access-Control-Allow-Origin: *`.

---

## Deterministic Financial Rule
> [!IMPORTANT]
> Balances are **NEVER** calculated by AI.
> $$\text{balance} = \sum \text{CREDIT} - \sum \text{PAYMENT}$$
> Bedrock (`bedrock_service.py:45`) extracts `customerName/type/amount/description` and generates WhatsApp replies; `ledger_service.py:239` computes balance via `Decimal(str(amount))`.

---

## Supported API Operations

### 1. WhatsApp Verification
- **Route**: `GET /whatsapp/webhook` (also `GET /whatsapp`)
- **Query**: `?hub.mode=subscribe&hub.verify_token=<WHATSAPP_VERIFY_TOKEN>&hub.challenge=<challenge>`
- **Success (`200 text/plain`)**: returns `hub.challenge` verbatim (Meta requirement)
- **Fail (`403`)**: `{"success":false,"error":"Verify token mismatch"}` or `WHATSAPP_VERIFY_TOKEN not configured`
- **Notes**: Supports `queryStringParameters` and `rawQueryString` (API GW v1/v2). Implemented via `whatsapp_service.verify_webhook()`. `GRAPH_VERSION` defaults `v18.0`.

### 2. WhatsApp Inbound (Text & Voice)
- **Route**: `POST /whatsapp/webhook` (also `POST /whatsapp`)
- **Headers**: `X-Hub-Signature-256: sha256=<hmac>` verified if `WHATSAPP_APP_SECRET` set via `whatsapp_service.verify_signature()`
- **Body** (Meta shape):
  ```json
  {
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "metadata": {"phone_number_id": "111"},
          "messages": [
            {"from": "919876543210", "id": "wamid.text1", "type": "text", "text": {"body": "Rahul took rice for 500 on credit"}},
            {"from": "919876543210", "id": "wamid.voice1", "type": "voice", "voice": {"id": "media_123", "mime_type": "audio/ogg"}}
          ]
        }
      }]
    }]
  }
  ```
- **Flow per message** (`handler.py:_process_whatsapp_single_message`):
  1. `text` → `raw_text`; `audio`/`voice` → `whatsapp_service.download_media(mediaId)` → `transcribe_service.transcribe_audio_bytes(bytes, media_format)` (mime → `ogg`/`mp3`/`mp4`/`wav`, S3 transient `whatsapp/{uuid}.ogg` → Transcribe `start_transcription_job` → poll 1s/30s → fetch `TranscriptFileUri` → S3 delete)
  2. `bedrock_service.extract_transaction(raw_text)` → validated `{customerName,type,amount,description}`
  3. `ledger_service.list_customers(shopId)` fuzzy find (exact lower, first-token) or `create_customer(shopId, name, phone=from)` → `add_transaction(shopId, customerId, type, amount, description)` → `updatedCustomerBalance` (deterministic)
  4. `bedrock_service.generate_reply(extracted, balance, raw_text)` → Hinglish (`REPLY_SYSTEM_PROMPT`) or fallback `Rahul ke khate me ₹500 udhar joda. Kul udhar: ₹1200. ✅` / `Rahul ne ₹300 jama kiye. Bacha udhar: ₹900. 🙏`
  5. `whatsapp_service.send_text(to=from, text=reply, phone_number_id)` best-effort (`skipped_no_token` if `WHATSAPP_TOKEN` blank)

- **Response (`200 OK`, always ack to prevent Meta retries)**:
  ```json
  {
    "success": true,
    "status": "processed",
    "count": 1,
    "results": [{
      "message_id": "wamid.voice1",
      "status": "processed",
      "from": "919876543210",
      "shopId": "shop001",
      "type": "voice",
      "transcript": "Rahul paid 300",
      "extractedTransaction": {"customerName":"Rahul","type":"PAYMENT","amount":300,"description":""},
      "customer": {"customerId":"cust_123","name":"Rahul"},
      "transaction": {"transactionId":"tx_456","updatedCustomerBalance":200},
      "balance": 200,
      "reply": "Rahul ne ₹300 jama kiye. Bacha udhar: ₹200. 🙏",
      "whatsapp_send": "sent",
      "transcription_meta": {"audio_bytes_len": 12345, "transcript": "Rahul paid 300"}
    }]
  }
  ```
- **Other statuses**: `skipped` (unsupported `image` etc), `failed` (`TranscriptionFailedError`/`BedrockExtractionError` — also sends WhatsApp error text `Voice note samajh nahi paya...` if possible), `error` with `code:503` (Bedrock/Transcribe/WhatsApp/Dynamo unavailable). Status updates (no `messages`) → `200 {"status":"received","processed":0}`.

### 3. Direct Transcribe (Testing without WhatsApp)
- **Route**: `POST /whatsapp/transcribe`
- **Body**:
  ```json
  {"s3_uri": "s3://ledgerly-whatsapp-audio/whatsapp/abc.ogg", "media_format": "ogg", "language_code": "en-IN"}
  {"audio_base64": "<base64 ogg bytes>", "media_format": "ogg"}
  ```
- **Success (`200`)**: `{"success":true,"transcript":"Rahul took rice for 500"}`
- **Errors**: `400 Transcription failed` (empty/timeout/silent), `503 Transcribe unavailable` (no `TRANSCRIBE_S3_BUCKET`/creds)

### 4. Natural-Language Ingestion (Text Only, No DB Write)
- **Route**: `POST /message` (or root `POST`)
- **Body**: `{"message": "Rahul took rice for 500 on credit"}`
- **Response (`200`)**:
  ```json
  {
    "success": true,
    "message": "Rahul took rice for 500 on credit",
    "status": "received",
    "extractedTransaction": {"customerName":"Rahul","type":"CREDIT","amount":500,"description":"rice"}
  }
  ```
- **Errors**: `400 Field 'message' is required/cannot be empty`, `400 Transaction extraction failed`, `503 Bedrock unavailable`

### 5. Create Customer
- **Route**: `POST /customers`
- **Body**: `{"shopId":"shop001","name":"Rahul","phone":"9876543210","customerId":"optional"}`
- **Response (`201`)**: `{"success":true,"customer":{"customerId":"cust_abc123","shopId":"shop001","name":"Rahul","phone":"9876543210","balance":0,"createdAt":"2026-09-17T14:18:00+00:00"}}`
- **Errors**: `400 Field '<name>' is required/cannot be empty`, `503 DynamoDB unavailable`

### 6. List Customers
- **Route**: `GET /customers?shopId=shop001`
- **Response (`200`)**: `{"success":true,"customers":[...],"count":1}`
- **Errors**: `400 Query parameter 'shopId' is required`, `503 DynamoDB unavailable`

### 7. Get Single Customer
- **Route**: `GET /customers/{customerId}?shopId=optional`
- **Response (`200`)**: `{"success":true,"customer":{...,"balance":500}}` or `404 Customer '...' not found`

### 8. Record Transaction
- **Route**: `POST /transactions`
- **Body**: `{"shopId":"shop001","customerId":"cust_123","type":"CREDIT|PAYMENT","amount":500,"description":"Rice","dueDate":"2026-09-20","transactionId":"optional"}`
- **Response (`201`)**:
  ```json
  {
    "success": true,
    "transaction": {
      "transactionId":"tx_xyz789","shopId":"shop001","customerId":"cust_123","type":"CREDIT","amount":500,
      "description":"Rice","dueDate":"2026-09-20","createdAt":"2026-09-17T14:20:00+00:00","updatedCustomerBalance":500
    }
  }
  ```
- **Errors**: `400 Field '<name>' is required/cannot be empty`, `400 Transaction type must be CREDIT or PAYMENT`, `400 amount must be greater than zero/numeric`, `503 DynamoDB unavailable`

### 9. Get Customer Transactions
- **Route**: `GET /customers/{customerId}/transactions?shopId=optional`
- **Response (`200`)**: `{"success":true,"customerId":"cust_123","balance":500,"transactions":[...],"count":1}` (sorted reverse `createdAt`)

---

## Validation & Error Handling

| Condition | Status | Body |
|---|---|---|
| Missing body / empty / invalid JSON | `400` | `Missing request body` / `Invalid JSON format` / `Request body must be a JSON object` |
| Empty `message`/customer/phone | `400` | `Field 'name' cannot be empty` |
| Invalid `type` / `amount <=0` / non-numeric | `400` | `Transaction type must be CREDIT or PAYMENT` / `amount must be greater than zero` |
| Transcription empty / silent | `400` | `Transcription failed: ... empty transcript` |
| Unsupported WhatsApp `type` (image etc) | `200` (ack) | `results[].status=skipped` |
| Bedrock extraction invalid JSON/type/amount | `400` | `Transaction extraction failed: ...` (also WhatsApp error reply) |
| DynamoDB/Transcribe/WhatsApp/Bedrock unconfigured | `503` | `... service is unavailable ... details` (WhatsApp webhook still returns `200` to avoid retries; `results[].code=503`) |
| `hub.verify_token` mismatch | `403` | `Verify token mismatch` |
| `X-Hub-Signature-256` invalid | `403` | `Invalid X-Hub-Signature-256` |
| Unknown route | `404` | `Route not found: METHOD path` |
| Method not `GET,POST` | `405` | `Method X not allowed.` |

---

## Environment Variables & Configuration

| Variable | Default | Purpose |
|---|---|---|
| `WHATSAPP_TOKEN` | *(none)* | Meta Graph API Bearer token |
| `WHATSAPP_PHONE_NUMBER_ID` | *(none)* | Phone number ID for sending |
| `WHATSAPP_VERIFY_TOKEN` | *(none)* | Webhook verification token |
| `WHATSAPP_APP_SECRET` | *(none)* | Optional HMAC for `X-Hub-Signature-256` |
| `WHATSAPP_GRAPH_VERSION` | `v18.0` | Graph API version (`whatsapp_service.py:32`) |
| `DEFAULT_SHOP_ID` | `shop001` | Fallback shop |
| `SHOP_PHONE_MAP` | *(none)* | JSON `{"phone_number_id":"shopId"}` |
| `TRANSCRIBE_S3_BUCKET` | *(none)* | S3 bucket for voice audio (required for voice) |
| `TRANSCRIBE_LANGUAGE` | `en-IN` | `en-IN`/`hi-IN`/`auto` |
| `MAX_VOICE_BYTES` | `10485760` | Max voice size |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` | Bedrock model |
| `AWS_REGION` | `us-east-1` | Region for all AWS services |
| `CUSTOMERS_TABLE` | `Customers` | Customers DynamoDB table |
| `TRANSACTIONS_TABLE` | `Transactions` | Transactions table |
| `DYNAMODB_ENDPOINT_URL` | *(none)* | Local `http://localhost:8000` |

Lambda needs timeout **60s** (Transcribe polling 30s + Graph 30s), memory 512MB.

---

## How DynamoDB/S3/Transcribe/Bedrock Will Be Connected

1. **DynamoDB**: Create `Customers` (PK `customerId` String) + `Transactions` (PK `transactionId` String); GSI `shopId`/`customerId` planned. IAM `dynamodb:GetItem/PutItem/UpdateItem/Scan/Query`.
2. **S3**: Create bucket `TRANSCRIBE_S3_BUCKET`, lifecycle delete 1d, IAM `s3:PutObject/GetObject/DeleteObject`.
3. **Transcribe**: IAM `transcribe:StartTranscriptionJob/GetTranscriptionJob/DeleteTranscriptionJob`; language `en-IN`.
4. **Bedrock**: Enable model in `AWS_REGION`; IAM `bedrock:InvokeModel`.
5. **WhatsApp**: Meta App → WABA → webhook `https://<apigw>/whatsapp/webhook` with `WHATSAPP_VERIFY_TOKEN`, subscribe `messages`.
