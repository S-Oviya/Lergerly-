# Ledgerly

Ledgerly is an AI-powered digital ledger designed to help local shopkeepers manage customer credit, payments, and outstanding balances.

My contribution focuses on the **backend ledger and transaction API**, providing the foundation for storing customers, recording transactions, and calculating balances.

## What I Worked On

### Backend API

Implemented a Python-based backend with a Lambda-compatible handler for handling ledger-related requests.

The backend currently supports:

* Customer creation
* Customer retrieval
* Customer listing
* Transaction creation
* Customer transaction history
* Message-based transaction input
* Request validation
* Error handling
* CORS handling

### Ledger Logic

Implemented the core ledger service using DynamoDB-compatible data access.

Transactions are represented as:

* `CREDIT` — money owed by the customer
* `PAYMENT` — money paid by the customer

The customer balance is calculated deterministically:

```text
Balance = Total Credits - Total Payments
```

The financial calculation is handled by the backend rather than an AI model.

### API Integration

Created the frontend API service in:

```text
src/services/api.ts
```

It provides typed functions for communicating with the backend, including:

```text
sendMessage()
createCustomer()
createTransaction()
```

The API base URL is configured through an environment variable.

### Validation & Testing

Added validation for:

* Missing request bodies
* Invalid JSON
* Missing messages
* Empty messages
* Invalid customer data
* Invalid transaction types
* Invalid transaction amounts

Added backend unit tests covering the main API and ledger scenarios.

Current backend test result:

```text
7/7 tests passing
```

## Backend Structure

```text
backend/
├── lambda/
│   ├── handler.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── ledger_service.py
│   └── tests/
│       ├── __init__.py
│       └── test_backend.py
├── requirements.txt
└── README.md
```

## Data Model

### Customer

```text
customerId
shopId
name
phone
balance
createdAt
```

### Transaction

```text
transactionId
shopId
customerId
type
amount
description
dueDate
createdAt
```

## API Endpoints

### `POST /message`

Accepts a natural-language transaction message.

Example:

```json
{
  "message": "Rahul took rice for 500 on credit"
}
```

### `POST /customers`

Creates a customer.

### `POST /transactions`

Records a credit or payment transaction.

Example:

```json
{
  "shopId": "shop-001",
  "customerId": "customer-001",
  "type": "CREDIT",
  "amount": 500,
  "description": "rice"
}
```

## Architecture of My Part

```text
Frontend
   │
   │ API Request
   ▼
Lambda Handler
   │
   ├── Validation
   │
   └── Ledger Service
           │
           ▼
       DynamoDB
           │
           ▼
   Customer / Transactions
           │
           ▼
   Deterministic Balance
```

The backend is designed so that the AI layer can provide structured transaction information while the ledger service remains responsible for storing transactions and calculating balances.

## Frontend API Layer

The frontend communicates with the backend through:

```text
src/services/api.ts
```

This keeps API communication separate from the UI components and allows the backend endpoint to be configured using:
               
```env
VITE_API_BASE_URL=
```

## Testing

Run the backend tests with:

```bash
python -m unittest backend/lambda/tests/test_backend.py -v
```

Build the frontend with:

```bash
npm run build
```

