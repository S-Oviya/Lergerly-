# Ledgerly API Contract (Current Lambda Backend)

This document specifies the exact HTTP API contract implemented in the AWS Lambda backend (`backend/lambda/handler.py` and `backend/lambda/services/ledger_service.py`).

All responses return standard CORS headers (`Access-Control-Allow-Origin: *`) and JSON payloads.

---

## 1. `POST /message` (Natural-Language Ingestion)

### Purpose
Ingestion endpoint for conversational transaction notes entered or spoken by a shopkeeper. Currently validates incoming payloads and acknowledges receipt.

*(Planned for Phase 3: Passing this text to Amazon Bedrock for entity extraction.)*

### Request JSON
| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | **Yes** | Natural language text note from the shopkeeper. Must not be empty. |

### Example Request
```http
POST /message
Content-Type: application/json

{
  "message": "Rahul took rice for 500 on credit"
}
```

### Successful Response (`200 OK`)
```json
{
  "success": true,
  "message": "Rahul took rice for 500 on credit",
  "status": "received"
}
```

### Validation & Error Responses (`400 Bad Request`)
- **Missing body**: `{"success": false, "error": "Missing request body"}`
- **Empty body**: `{"success": false, "error": "Request body cannot be empty"}`
- **Invalid JSON**: `{"success": false, "error": "Invalid JSON format"}`
- **Missing field**: `{"success": false, "error": "Field 'message' is required"}`
- **Empty string**: `{"success": false, "error": "Field 'message' cannot be empty"}`
- **Non-string type**: `{"success": false, "error": "Field 'message' must be a string"}`

---

## 2. `POST /customers` (Create Customer)

### Purpose
Creates a new customer account under a specific shop.

### Required Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `shopId` | string | **Yes** | Identifier of the shopkeeper's store (e.g., `"shop001"`). |
| `name` | string | **Yes** | Customer full name (e.g., `"Rahul Sharma"`). |
| `phone` | string | **Yes** | Customer contact phone number. |
| `customerId` | string | No | Optional custom ID. If omitted, backend generates one (e.g., `cust_...`). |

### Example Request
```http
POST /customers
Content-Type: application/json

{
  "shopId": "shop001",
  "name": "Rahul Sharma",
  "phone": "+91 98765 43210"
}
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

### Validation & Error Responses
- **Missing / Empty Required Field (`400 Bad Request`)**:  
  `{"success": false, "error": "Field '<name>' is required"}` or `{"success": false, "error": "Field '<name>' cannot be empty"}`
- **Unconfigured DynamoDB (`503 Service Unavailable`)**:  
  `{"success": false, "error": "DynamoDB service is unavailable or not configured...", "details": "..."}`

---

## 3. `POST /transactions` (Record Transaction)

### Purpose
Appends a credit or payment entry to the customer's ledger and deterministically updates the customer's account balance.

### Required Fields & Allowed Types
| Field | Type | Required | Constraints / Description |
|---|---|---|---|
| `shopId` | string | **Yes** | Store identifier. Must not be empty. |
| `customerId` | string | **Yes** | Customer identifier. Must not be empty. |
| `type` | string | **Yes** | Must be either `"CREDIT"` or `"PAYMENT"`. |
| `amount` | number | **Yes** | Transaction value in INR. Must be strictly greater than 0. |
| `description` | string | No | Optional goods note or item description. |
| `dueDate` | string | No | Optional promised payment date (e.g., `"2026-09-20"`). |
| `transactionId`| string | No | Optional custom transaction ID. Auto-generated if omitted. |

### Allowed Transaction Types:
- **`CREDIT`**: Customer took items on credit (*udhar*). Increases balance owed.
- **`PAYMENT`**: Customer made a cash/UPI payment. Decreases balance owed.

### Example Request 1: CREDIT Purchase
```http
POST /transactions
Content-Type: application/json

{
  "shopId": "shop001",
  "customerId": "cust_9e7f6a2b1c0d",
  "type": "CREDIT",
  "amount": 500,
  "description": "2 packets of basmati rice",
  "dueDate": "2026-09-20"
}
```

### Example Request 2: PAYMENT Settlement
```http
POST /transactions
Content-Type: application/json

{
  "shopId": "shop001",
  "customerId": "cust_9e7f6a2b1c0d",
  "type": "PAYMENT",
  "amount": 300,
  "description": "Partial cash payment"
}
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

### Validation & Error Responses
- **Missing Required Fields (`400 Bad Request`)**:  
  `{"success": false, "error": "Field '<name>' is required"}`
- **Invalid Type (`400 Bad Request`)**:  
  `{"success": false, "error": "Transaction type must be CREDIT or PAYMENT"}`
- **Invalid Amount (`400 Bad Request`)**:  
  `{"success": false, "error": "amount must be greater than zero"}`
- **Unconfigured DynamoDB (`503 Service Unavailable`)**:  
  `{"success": false, "error": "DynamoDB service is unavailable or not configured...", "details": "..."}`

---

## 4. Deterministic Financial Rule

In Ledgerly, financial arithmetic is strictly deterministic and handled exclusively by backend code:

$$\text{Customer Balance} = \sum \text{Total CREDIT} - \sum \text{Total PAYMENT}$$

- **CREDIT** transactions add to the balance ($+$).
- **PAYMENT** transactions subtract from the balance ($-$).
- **No LLM Calculation**: The AI model (Amazon Bedrock) is only used for entity extraction from text; it is **never** permitted to calculate balances.

---

## 5. Frontend Integration Notes (Planned for Phase 4)

Currently, the React frontend runs locally with mock data and deterministic client-side calculation rules. When integrating with this backend in Phase 4:

1. **Base URL Configuration**:
   - The frontend will configure an environment variable: `VITE_API_BASE_URL` pointing to the deployed Amazon API Gateway endpoint (or local mock server).
2. **Shop Identification**:
   - The frontend should include a fixed `shopId` (e.g. `"shop001"`) in customer and transaction payloads.
3. **Voice & Text Command Bar**:
   - The frontend natural language input bar will send `{ "message": userText }` to `POST /message`.
4. **Manual Forms & Modals**:
   - The "Add Customer" modal will send `{ shopId, name, phone }` to `POST /customers`.
   - The "Add Transaction" modal will send `{ shopId, customerId, type, amount, description, dueDate }` to `POST /transactions`.
5. **Synchronous Balance Updates**:
   - `POST /transactions` returns `updatedCustomerBalance` in the response, allowing the React UI to update the customer's balance badge without a separate round trip.
