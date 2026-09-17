# Ledgerly - Backend Services & AWS Architecture

This directory houses the backend logic and serverless infrastructure for **Ledgerly**.

---

## Directory Layout
```text
backend/
├── lambda/
│   ├── handler.py                   # AWS Lambda entrypoint (API Gateway router & validator)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── bedrock_service.py       # Amazon Bedrock entity extraction service
│   │   └── ledger_service.py        # DynamoDB data layer & deterministic balance math
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_backend.py          # Lightweight unittest suite (no AWS/network required)
│   └── README.md                    # Lambda API specifications & contract details
├── requirements.txt                 # Python dependencies (boto3, botocore)
└── README.md                        # Architecture overview & testing guide
```

---

## Architecture Flow

```
React Frontend (Voice / Text)
      │ (HTTPS POST / GET)
      ▼
Amazon API Gateway (/customers, /transactions, /message)
      │ (Lambda Proxy Integration)
      ▼
AWS Lambda (backend/lambda/handler.py)
      │
      ├──> [Phase 3] Amazon Bedrock (via services/bedrock_service.py)
      │      └── Extracts: customerName, type (CREDIT/PAYMENT), amount, description
      │
      └──> [Phase 4] Amazon DynamoDB (via services/ledger_service.py)
             ├── Customers Table (customerId, shopId, name, phone, balance, createdAt)
             └── Transactions Table (transactionId, shopId, customerId, type, amount, dueDate, createdAt)
```

---

## Amazon Bedrock Configuration

The extraction service uses the AWS Bedrock runtime client (`boto3.client('bedrock-runtime')`).

| Environment Variable | Default | Purpose |
|---|---|---|
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` | Bedrock Foundation Model ID for structured JSON extraction |
| `AWS_REGION` | `us-east-1` | AWS region where Bedrock model access is enabled |

### Financial Rule:
> [!IMPORTANT]
> Amazon Bedrock is strictly used for natural language entity extraction.
> Customer balance arithmetic (`balance = total CREDIT - total PAYMENT`) is strictly computed deterministically by backend code, **never** by the AI model.

---

## Running the Unit Test Suite

The backend includes a self-contained test suite using Python's built-in `unittest` framework. It runs completely offline without requiring live AWS credentials or live DynamoDB/Bedrock calls.

### Run All Tests:
```powershell
python -m unittest backend/lambda/tests/test_backend.py -v
```

Or via test discovery:
```powershell
python -m unittest discover -s backend/lambda/tests -v
```

### Test Coverage (17 Tests):
- **Bedrock Entity Extraction**:
  - `Rahul took rice for 500 on credit` $\rightarrow$ `CREDIT` / `500` / `Rahul` / `rice`
  - `Rahul paid 300` $\rightarrow$ `PAYMENT` / `300` / `Rahul` / `""`
  - Non-JSON / malformed model output $\rightarrow$ Handled error (`BedrockExtractionError`)
  - Empty model output $\rightarrow$ Handled error (`BedrockExtractionError`)
  - Unsupported transaction type (e.g. `TRANSFER`) $\rightarrow$ Handled error (`BedrockExtractionError`)
  - Non-positive or non-numeric amount $\rightarrow$ Handled error (`BedrockExtractionError`)
  - Missing/empty `customerName` $\rightarrow$ Handled error (`BedrockExtractionError`)
- **Lambda Handler**:
  - `POST /message` with valid note $\rightarrow$ Returns HTTP `200` with `extractedTransaction`
  - `POST /message` with Bedrock service offline $\rightarrow$ Returns HTTP `503 Service Unavailable`
  - `POST /message` with invalid extraction $\rightarrow$ Returns HTTP `400 Bad Request`
  - Missing/empty message field validation $\rightarrow$ HTTP `400`
  - Customer creation validation $\rightarrow$ HTTP `400`
  - Transaction creation validation $\rightarrow$ HTTP `400`
- **Deterministic Ledger Math**:
  - `balance = total CREDIT - total PAYMENT` (Credits $500 + 250 = 750$, Payment $300 \rightarrow 450$)
