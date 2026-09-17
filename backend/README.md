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
React Frontend
      │ (HTTPS POST / GET)
      ▼
Amazon API Gateway (/customers, /transactions, /message)
      │ (Lambda Proxy Integration)
      ▼
AWS Lambda (backend/lambda/handler.py)
      │
      ├──> [Phase 3] Amazon Bedrock (Entity extraction from natural language)
      │
      └──> [Phase 4] Amazon DynamoDB (via services/ledger_service.py)
             ├── Customers Table (customerId, shopId, name, phone, balance, createdAt)
             └── Transactions Table (transactionId, shopId, customerId, type, amount, dueDate, createdAt)
```

---

## Running the Unit Test Suite

The backend includes a self-contained test suite using Python's built-in `unittest` framework. It runs completely offline without requiring AWS credentials or live DynamoDB tables.

### Run All Tests:
```powershell
python -m unittest backend/lambda/tests/test_backend.py -v
```

Or via test discovery:
```powershell
python -m unittest discover -s backend/lambda/tests -v
```

### Test Coverage Includes:
- **`valid POST /message request`**: Asserts HTTP `200` with confirmation payload.
- **`missing message field`**: Asserts HTTP `400` with `"Field 'message' is required"`.
- **`empty message field`**: Asserts HTTP `400` with `"Field 'message' cannot be empty"`.
- **`invalid customer payload`**: Asserts HTTP `400` when missing required customer fields (e.g. phone).
- **`invalid transaction type`**: Asserts HTTP `400` when type is not `CREDIT` or `PAYMENT`.
- **`non-positive transaction amount`**: Asserts HTTP `400` when amount is `<= 0`.
- **`deterministic balance calculation`**: Asserts that `balance = total CREDIT - total PAYMENT` (Credits `500 + 250`, Payment `300` $\rightarrow$ `450`).

---

## Local Ad-Hoc Testing
You can also run quick manual invocations against the Lambda handler:

```powershell
# Test message ingestion
python -c "
import json, sys
sys.path.insert(0, 'backend/lambda')
import handler
res = handler.lambda_handler({'httpMethod': 'POST', 'body': json.dumps({'message': 'Rahul took rice for 500 on credit'})})
print('Status:', res['statusCode'])
print('Body:', res['body'])
"
```
