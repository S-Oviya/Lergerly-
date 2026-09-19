# WhatsApp Messaging & Bill Generation Layer

This document details the reusable WhatsApp message-generation layer for **Ledgerly**.

---

## 1. System Responsibilities & Architecture Boundaries

In the Ledgerly architecture, system responsibilities are partitioned as follows:

| System Layer | Subsystem | Responsibilities |
|---|---|---|
| **Bedrock / AI Extraction** | **AI / Extraction Layer** | Voice-to-text integration, Amazon Bedrock Claude 3 extraction of natural-language kirana notes into structured JSON. |
| **Deterministic Ledger & DynamoDB** | **Ledger Layer** | DynamoDB data access, transaction history persistence, and deterministic customer balance calculation (`balance = total CREDIT - total PAYMENT`). |
| **WhatsApp Message Generation** | **Messaging Service** | Pure deterministic formatting of customer-facing WhatsApp confirmations, payment receipts, and digital bills from structured transaction data. |
| **Meta Cloud API Transport** | **WhatsApp Transport** | Dispatching prepared messages through Meta's official WhatsApp Business Cloud API. |

### Strict Boundaries
- **No Balance Calculation**: Messaging services (`bill_service.py` and `message_templates.py`) **never** calculate or modify customer balances. Deterministic balance math is strictly owned by `ledger_service.py`.
- **No Direct DynamoDB Queries**: Messaging services operate purely on structured data passed into the service; they do not read or write to DynamoDB tables.
- **No Direct Bedrock Invocations**: Entity extraction is completed before transaction data reaches this layer.
- **No Live Meta API Calls in this Phase**: This phase establishes the message-generation contract and testing suite. Meta Cloud API network calls are handled by `whatsapp_service.py`.

---

## 2. End-to-End Message Generation Flow

```text
Shopkeeper Spoken Kirana Note
             ↓
Browser Speech Recognition (Web Speech API)
             ↓
POST /message (API Gateway / Lambda)
             ↓
Amazon Bedrock Extraction
             ↓
Structured Transaction Data
             ↓
Ledger Service & DynamoDB Storage
             ↓
BillService.generate_bill()
             ↓
WhatsApp-Ready Formatted Text
             ↓
WhatsAppService -> Meta WhatsApp Cloud API
             ↓
Customer WhatsApp Notification
```

---

## 3. Input Structure Expected by Messaging Services

`BillService` accepts structured transaction dictionaries formatted in either **camelCase** (standard API Gateway/frontend contract) or **snake_case** (Python backend service convention).

### Schema Specification

```json
{
  "customerName": "Rahul",
  "type": "CREDIT",
  "amount": 500,
  "description": "Rice",
  "dueDate": "20 Sep 2026"
}
```

### Field Definitions

| Field Name (camelCase / snake_case) | Type | Required? | Allowed Values / Constraints | Description |
|---|---|---|---|---|
| `customerName` / `customer_name` | `string` | **Yes** | Non-empty, non-whitespace string | Customer's registered name |
| `type` / `transaction_type` / `tx_type` | `string` | **Yes** | `"CREDIT"` or `"PAYMENT"` (case-insensitive) | Nature of ledger entry |
| `amount` | `number` / `string` / `Decimal` | **Yes** | Numeric value `> 0` | Transaction value in INR |
| `description` / `itemsNote` / `item` | `string` | No | Any text (or omitted/empty) | Kirana item or payment notes |
| `dueDate` / `due_date` | `string` | No | Date string (or omitted/empty) | Promised payment settlement date |

---

## 4. Message Specifications & Output Examples

### A. Transaction Confirmation (`render_transaction_confirmation` / `generate_bill`)

Used when recording a customer purchase or general credit transaction.

#### Full Credit Transaction (with Item and Due Date)
**Input:**
```python
tx = {
    "customerName": "Rahul",
    "type": "CREDIT",
    "amount": 500,
    "description": "Rice",
    "dueDate": "20 Sep 2026"
}
```

**WhatsApp Output:**
```text
Ledgerly
Transaction recorded

Customer: Rahul
Item: Rice
Amount: ₹500
Status: Credit
Due date: 20 Sep 2026
```

#### Credit Transaction (without Optional Due Date)
**Input:**
```python
tx = {
    "customerName": "Anita",
    "type": "CREDIT",
    "amount": 350,
    "description": "Cooking Oil"
}
```

**WhatsApp Output:**
```text
Ledgerly
Transaction recorded

Customer: Anita
Item: Cooking Oil
Amount: ₹350
Status: Credit
```

---

### B. Payment Confirmation (`render_payment_confirmation` / `generate_payment_receipt`)

Used specifically when a customer makes a cash or digital payment against their outstanding balance.

#### Example
**Input:**
```python
payment = {
    "customerName": "Rahul",
    "amount": 500
}
```

**WhatsApp Output:**
```text
Ledgerly
Payment recorded

Customer: Rahul
Amount paid: ₹500
```

---

## 5. Pure Formatting Rules & Validation

1. **Currency Formatting (`format_inr`)**:
   - Strictly positive numeric input (`> 0`). Non-numeric, zero, negative, or `NaN` inputs raise `TemplateValidationError`.
   - Integer values render cleanly without decimal noise: `500` -> `₹500`, `1000` -> `₹1,000`.
   - Fractional values preserve two decimal places: `1250.5` -> `₹1,250.50`.
2. **Deterministic String Construction**:
   - Pure string interpolation without external side effects or dependencies.
   - Preserves UTF-8 special characters, store notations, and symbols (e.g. `M/s. Sharma & Sons (Kirana)`, `@ ₹45/kg`).
3. **Optional Field Omitting**:
   - If `description` is missing or empty, the `Item:` line is omitted.
   - If `dueDate` is missing or empty, the `Due date:` line is omitted.

---

## 6. Financial Rule Isolation: Balance Calculation Ownership

> [!IMPORTANT]
> **Deterministic Balance Calculation is Strictly Owned by LedgerService.**
>
> Customer balances in Ledgerly are computed exclusively via:
> $$\text{balance} = \sum \text{CREDIT} - \sum \text{PAYMENT}$$
>
> - `message_templates.py` and `bill_service.py` **do not calculate, store, or modify balances**.
> - Balance numbers must always originate from `ledger_service.calculate_customer_balance()`.
> - AI models (Amazon Bedrock) are prohibited from computing financial balances.

---

## 7. Future Connection Point: Meta WhatsApp Cloud API

When live WhatsApp messaging is connected in the next automation milestone, `BillService` will integrate with `WhatsAppService`:

```python
# Future Integration Blueprint (Meta WhatsApp Cloud API)
class WhatsAppService:
    def __init__(self, api_token: str, phone_number_id: str):
        self.api_token = api_token
        self.phone_number_id = phone_number_id
        self.bill_service = BillService()

    def send_transaction_notification(self, customer_phone: str, transaction: dict) -> dict:
        # 1. Generate formatted message via BillService
        message_text = self.bill_service.generate_bill(transaction)

        # 2. Transmit via Meta Cloud API
        payload = {
            "messaging_product": "whatsapp",
            "to": customer_phone,
            "type": "text",
            "text": {"body": message_text}
        }
        # POST https://graph.facebook.com/v18.0/{phone_number_id}/messages
        ...
```

Because `BillService` is isolated from the HTTP client, messaging logic can be tested 100% locally with zero cloud dependencies or mock credentials.
