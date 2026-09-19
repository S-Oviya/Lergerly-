# Ledgerly WhatsApp Payment-Reply Handling

This document details customer payment-reply automation on WhatsApp for Ledgerly.

---

## 1. Overview

When customers send messages confirming payments (e.g. *"I paid ₹500"*), the system deterministically recognizes the payment intent, records a `PAYMENT` transaction in the existing ledger without invoking generative LLMs for extraction, computes the new balance, and sends a localized WhatsApp confirmation.

---

## 2. Supported Examples

The deterministic parser (`PaymentReplyService`) extracts the numeric amount and flags the action as `PAYMENT` for patterns including:

- `"I paid ₹500"`
- `"paid 500"`
- `"₹500 paid"`
- `"payment done 500"`
- `"payment made 500"`
- `"I have paid Rs 500"`
- `"I've paid ₹1,000"`
- `"paid Rs. 750"`
- `"payment of ₹500 done"`
- `"₹10,000 paid"`
- `"Rs 1,500 paid"`
- `"Rs. 2,500 payment done"`
- Hinglish/multilingual: `"500 jama kiya"`, `"bhugtan 500 done"`

Numbers formatted with commas (e.g. `₹1,000`, `Rs 10,000`) are normalized into valid numbers.

---

## 3. Ambiguous & Rejected Examples

Messages with payment keywords but without a positive numeric amount are flagged as `AMBIGUOUS`:

- `"paid"`
- `"I paid"`
- `"I paid everything"`
- `"payment done"`
- `"settled"`
- Non-positive amounts: `"paid 0"`, `"paid -500"`

**Behavior:** The handler does **not** create a ledger transaction for ambiguous messages. Instead, it prompts the customer for clarification (e.g., *"Please specify the payment amount (e.g. 'I paid ₹500')."*).

---

## 4. Parser Output Structure

`PaymentReplyService.parse(text, customer_name=None, language=None)` returns:

### Clear Payment Match
```json
{
  "action": "PAYMENT",
  "amount": 500,
  "customerName": "Rahul",
  "source": "whatsapp",
  "language": "hi-IN"
}
```

### Ambiguous Match
```json
{
  "action": "AMBIGUOUS",
  "amount": null,
  "customerName": "Rahul",
  "source": "whatsapp",
  "language": "hi-IN"
}
```

### Non-Payment Match
For normal transaction notes such as *"Rahul bought rice for ₹500"*, the parser returns `None`.

---

## 5. Ledger Integration

`LedgerService` remains the single source of truth:

1. **Customer Identification:**
   - The sender's phone number (`from_number`) is matched against existing customers via `ledger_service.list_customers(shop_id)`.
   - If not found, a customer record is created or retrieved via `_find_or_create_customer`.

2. **Transaction Recording:**
   - A transaction is written via `ledger_service.add_transaction(...)`:
     - `tx_type = "PAYMENT"`
     - `amount = <parsed_amount>`
     - `shopId = <shop_id>`
     - `customerId = <customer_id>`
     - `description = "Customer payment via WhatsApp"`
     - `transactionId = "wa_<message_id>"`
     - `language = <norm_lang>`

3. **Deterministic Balance:**
   - `LedgerService` computes the customer's balance (`total CREDIT - total PAYMENT`).
   - The updated balance is used directly for generating the WhatsApp acknowledgment.

---

## 6. Duplicate Safety / Idempotency

- Incoming WhatsApp messages include a unique Meta `message_id`.
- The transaction ID is set to `wa_<message_id>`.
- Prior to creating a transaction, the handler queries `ledger_service.get_customer_transactions(customer_id, shop_id)`.
- If a transaction with `transactionId == wa_<message_id>` already exists, re-insertion is bypassed, the existing balance is returned, and `duplicate: True` is flagged.

---

## 7. Handler Routing Pipeline

```
Inbound WhatsApp Webhook (POST /whatsapp/webhook)
  │
  ├─► Download & Transcribe (if audio/voice) OR extract text
  │
  ├─► PaymentReplyService.parse(raw_text)
  │     │
  │     ├─► action == "PAYMENT"
  │     │     ├─ Lookup customer by sender phone / name
  │     │     ├─ Check idempotency (wa_<message_id>)
  │     │     ├─ LedgerService.add_transaction(type="PAYMENT", amount)
  │     │     ├─ Obtain deterministic updatedCustomerBalance
  │     │     ├─ Send localized WhatsApp acknowledgment
  │     │     └─ STOP (normal CREDIT flow bypassed)
  │     │
  │     ├─► action == "AMBIGUOUS"
  │     │     ├─ Send clarification message asking for amount
  │     │     └─ STOP (no ledger entry created)
  │     │
  │     └─► None (Not a payment reply)
  │           └─ Continue normal flow:
  │                Bedrock extraction -> Customer lookup -> CREDIT transaction -> Reply
```
