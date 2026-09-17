# Ledgerly - AWS Lambda Transaction & Data Layer Handler

## Overview
This AWS Lambda function (`handler.py`) and its supporting service (`services/ledger_service.py`) form the serverless backend foundation for **Ledgerly**.

It handles API Gateway requests for:
1. **Natural-language message ingestion** (`POST /message` or fallback `POST`)
2. **Customer account management** (`POST /customers`, `GET /customers`, `GET /customers/{customerId}`)
3. **Transaction logging & balance calculation** (`POST /transactions`, `GET /customers/{customerId}/transactions`)

All responses automatically include CORS headers and enforce deterministic financial arithmetic.

---

## Deterministic Financial Rule
> [!IMPORTANT]
> Customer balances are **NEVER** calculated by an AI model.
> Balances are computed deterministically by backend code:
> $$\text{balance} = \sum \text{CREDIT} - \sum \text{PAYMENT}$$

---

## Supported API Operations

### 1. Natural-Language Ingestion
- **Route**: `POST /message` (or root `POST`)
- **Body**:
  ```json
  {
    "message": "Rahul took rice for 500 on credit"
  }
  ```
- **Response (`200 OK`)**:
  ```json
  {
    "success": true,
    "message": "Rahul took rice for 500 on credit",
    "status": "received"
  }
  ```

### 2. Create Customer
- **Route**: `POST /customers`
- **Body**:
  ```json
  {
    "shopId": "shop001",
    "name": "Rahul",
    "phone": "9876543210"
  }
  ```
- **Response (`201 Created`)**:
  ```json
  {
    "success": true,
    "customer": {
      "customerId": "cust_abc123",
      "shopId": "shop001",
      "name": "Rahul",
      "phone": "9876543210",
      "balance": 0,
      "createdAt": "2026-09-17T14:18:00Z"
    }
  }
  ```

### 3. List Customers
- **Route**: `GET /customers?shopId=shop001`
- **Response (`200 OK`)**:
  ```json
  {
    "success": true,
    "customers": [...],
    "count": 1
  }
  ```

### 4. Get Single Customer
- **Route**: `GET /customers/{customerId}`
- **Response (`200 OK`)**:
  ```json
  {
    "success": true,
    "customer": {
      "customerId": "customer001",
      "shopId": "shop001",
      "name": "Rahul",
      "phone": "9876543210",
      "balance": 500,
      "createdAt": "2026-09-17T14:18:00Z"
    }
  }
  ```

### 5. Record Transaction
- **Route**: `POST /transactions`
- **Body**:
  ```json
  {
    "shopId": "shop001",
    "customerId": "customer001",
    "type": "CREDIT",
    "amount": 500,
    "description": "Rice",
    "dueDate": "2026-09-20"
  }
  ```
- **Response (`201 Created`)**:
  ```json
  {
    "success": true,
    "transaction": {
      "transactionId": "tx_xyz789",
      "shopId": "shop001",
      "customerId": "customer001",
      "type": "CREDIT",
      "amount": 500,
      "description": "Rice",
      "dueDate": "2026-09-20",
      "createdAt": "2026-09-17T14:20:00Z",
      "updatedCustomerBalance": 500
    }
  }
  ```

### 6. Get Customer Transactions
- **Route**: `GET /customers/{customerId}/transactions`
- **Response (`200 OK`)**:
  ```json
  {
    "success": true,
    "customerId": "customer001",
    "balance": 500,
    "transactions": [...],
    "count": 1
  }
  ```

---

## Validation & Error Handling

- **Missing Required Fields**: Returns `400 Bad Request` with `{"success": false, "error": "Field '<name>' is required"}`.
- **Empty Strings/IDs**: Returns `400 Bad Request` with `{"success": false, "error": "Field '<name>' cannot be empty"}`.
- **Invalid Type**: Returns `400 Bad Request` if `type` is not `CREDIT` or `PAYMENT`.
- **Amount Validation**: Returns `400 Bad Request` if `amount <= 0` or non-numeric.
- **Offline / Unconfigured DynamoDB**: Returns `503 Service Unavailable` with clean actionable diagnostics (never crashes the Lambda runtime).

---

## Environment Variables & Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CUSTOMERS_TABLE` | `Customers` | DynamoDB table name for customer records |
| `TRANSACTIONS_TABLE` | `Transactions` | DynamoDB table name for credit/payment ledgers |
| `AWS_REGION` | `us-east-1` | AWS region hosting DynamoDB |
| `DYNAMODB_ENDPOINT_URL` | *(None)* | Optional local DynamoDB endpoint (e.g. `http://localhost:8000`) for offline testing |

---

## How DynamoDB Will Be Connected Later

When deploying to AWS:

1. **Create DynamoDB Tables**:
   - **`Customers` Table**:
     - Partition Key: `customerId` (String)
     - Global Secondary Index (GSI): `shopId` (String) for shop customer listing
   - **`Transactions` Table**:
     - Partition Key: `transactionId` (String)
     - Global Secondary Index (GSI): `customerId` (String) for transaction history querying
2. **Assign IAM Permissions**:
   - Grant the Lambda execution role `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:Scan`, and `dynamodb:Query` on both tables.
3. **Configure Environment Variables**:
   - Set `CUSTOMERS_TABLE` and `TRANSACTIONS_TABLE` in the Lambda function configuration.
