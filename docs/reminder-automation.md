# Debt-Reminder Automation Layer

This document describes the local debt-reminder automation layer for **Ledgerly** (WhatsApp + Automation).

---

## 1. Role & Architectural Boundaries

In Ledgerly's architecture, responsibilities are strictly separated across layers:

| System Layer | Subsystem | Responsibilities |
|---|---|---|
| **AI / Extraction Layer** | **AI / Extraction Layer** | Voice-to-text processing, Amazon Bedrock extraction of natural-language notes into structured transactions. |
| **Ledger & Financial State** | **Ledger Layer** | DynamoDB data layer, customer balances, calculating outstanding debts via $\text{balance} = \sum \text{CREDIT} - \sum \text{PAYMENT}$. |
| **Reminder Automation & Messaging** | **Reminder Service** | Pure evaluation of supplied records against an injected calendar date, duplicate reminder suppression, and customer-facing WhatsApp reminder generation. |
| **WhatsApp Delivery Integration** | **WhatsApp Service** | Dispatching candidate messages via Meta WhatsApp Cloud API. |
| **Scheduler Automation** | **Scheduler** | Automated recurring cron triggers via AWS EventBridge Scheduler. |

### Strict Financial Boundary

> [!IMPORTANT]
> **The ReminderService NEVER calculates customer balances or financial aggregates.**
>
> It does not calculate:
> - Customer balance
> - Total amount owed
> - Outstanding balance
> - Accumulated credit across purchases
> - Payment history
> - Amount remaining after partial payments
>
> Those calculations are strictly the ledger service's responsibility.
>
> If the ledger passes `{ "customerName": "Rahul", "amount": 500, "dueDate": "2026-09-20" }`, ReminderService treats **₹500** as the exact amount to communicate.
> If a customer has multiple outstanding credit entries, ReminderService processes each transaction independently and **never sums them into a customer-level balance**.

---

## 2. Message Generation Workflow

```text
Ledger / Storage Layer (DynamoDB)
        ↓
Provides already-structured outstanding transaction record(s)
        ↓
ReminderService (services/reminder_service.py)
        ↓
Evaluates transaction due date against injected `today`
        ↓
Determines status: DUE / OVERDUE
        ↓
Generates WhatsApp-ready reminder (services/reminder_templates.py)
        ↓
WhatsApp Business Cloud API
        ↓
Customer WhatsApp Notification
```

---

## 3. Input Specification Expected from Ledger Layer

`ReminderService` accepts already-structured transaction dictionaries adhering to standard repository conventions:

```json
{
  "id": "txn-001",
  "customerName": "Rahul",
  "amount": 500,
  "dueDate": "2026-09-20",
  "type": "CREDIT",
  "lastReminderDate": "2026-09-19"
}
```

### Supported Fields
- `id` / `transactionId` / `transaction_id`: Transaction unique identifier.
- `customerName` / `customer_name`: Non-empty customer name string.
- `amount`: Numeric transaction value ($> 0$). Passed through unchanged.
- `dueDate` / `due_date`: Date or date string (`YYYY-MM-DD` or `DD Mon YYYY`).
- `type` / `transaction_type`: `"CREDIT"` or `"PAYMENT"`. (*Payment transactions are ignored; only credit entries with due dates receive payment reminders*).
- `lastReminderDate` / `last_reminder_date` *(optional)*: Last calendar date on which a reminder was dispatched.

---

## 4. Reminder Rules & Logic

The service requires an explicit `today: date` parameter. It **never** reads the system clock internally, ensuring complete determinism in tests and scheduled runs.

1. **Future Due Date (`dueDate > today`)**:
   - Return `None` (no reminder needed yet).

2. **Due Today (`dueDate == today`)**:
   - Status: `DUE`
   - Invokes `render_due_reminder(...)`.

3. **Overdue (`dueDate < today`)**:
   - Status: `OVERDUE`
   - Calculates $\text{days\_overdue} = \text{today} - \text{due\_date}$ (calendar date difference, **not** a financial calculation).
   - Invokes `render_overdue_reminder(...)`.

4. **Duplicate Reminder Protection**:
   - If `lastReminderDate == today`, suppress the duplicate (`None`).
   - If `lastReminderDate < today` and the transaction is still overdue, a new reminder candidate is generated.

---

## 5. Candidate Output Structure & WhatsApp Templates

### A. Due Reminder (`DUE`)

**Candidate Dictionary:**
```json
{
  "transaction_id": "txn-001",
  "customer_name": "Rahul",
  "amount": 500,
  "due_date": "2026-09-20",
  "status": "DUE",
  "message": "Ledgerly\n\nPayment reminder\n\nHi Rahul,\n\nYour payment of ₹500 is due today.\n\nDue date: 20 Sep 2026\n\nPlease make the payment when convenient."
}
```

**WhatsApp Message:**
```text
Ledgerly

Payment reminder

Hi Rahul,

Your payment of ₹500 is due today.

Due date: 20 Sep 2026

Please make the payment when convenient.
```

---

### B. Overdue Reminder (`OVERDUE`)

**Candidate Dictionary:**
```json
{
  "transaction_id": "txn-001",
  "customer_name": "Rahul",
  "amount": 500,
  "due_date": "2026-09-20",
  "status": "OVERDUE",
  "days_overdue": 3,
  "message": "Ledgerly\n\nPayment reminder\n\nHi Rahul,\n\nA payment of ₹500 was due on 20 Sep 2026.\n\nIt is now 3 days overdue.\n\nPlease make the payment when convenient."
}
```

**WhatsApp Message:**
```text
Ledgerly

Payment reminder

Hi Rahul,

A payment of ₹500 was due on 20 Sep 2026.

It is now 3 days overdue.

Please make the payment when convenient.
```

---

## 6. Future Architecture: AWS EventBridge Scheduler Integration

In future infrastructure milestones, automated recurring notifications will be scheduled as follows:

```text
AWS EventBridge Scheduler (Daily Cron e.g. cron(0 4 * * ? *))
        ↓
AWS Lambda (Reminder Dispatcher Function)
        ↓
DynamoDB / Ledger Query (Fetch pending transactions with due dates)
        ↓
ReminderService (Evaluate due & overdue candidates)
        ↓
Reminder Templates (Render WhatsApp text)
        ↓
Meta WhatsApp Business Cloud API (POST /v18.0/{phone_number_id}/messages)
        ↓
Customer Mobile Notification
```

> [!NOTE]
> **AWS EventBridge Scheduler is documented for future architecture only.**
> No EventBridge schedules, AWS clients, or live Meta API connections are provisioned in this phase. The current implementation is 100% local, dependency-free, and covered by automated unit tests.
