# Ledgerly 📒⚡
> **AI-Powered Credit & Payment Assistant for Small Shopkeepers (Kirana Stores)**  
> Built for the **WeMakeDevs + AWS "First Commit" Hackathon** (September 17–20, 2026).

---

## 📌 What is Ledgerly?
**Ledgerly** is a conversational AI ledger assistant that frees small kirana store owners and local merchants from cumbersome manual notebook keeping (*bahi-khata*). Shopkeepers can speak or type quick natural-language transaction notes in their everyday conversational style, and Ledgerly automatically extracts transaction details, updates customer balances deterministically, and issues clear confirmations.

---

## 🔍 The Problem
Across India and emerging markets, millions of micro-merchants and kirana shopkeepers rely on customer credit (*udhar*) as the lifeblood of customer loyalty. However:
1. **Manual Notebooks (*Bahi-Khata*)**: Prone to missing records, math errors, damage, and misplaced entries during busy store hours.
2. **Fragmented Messaging**: WhatsApp messages or scraps of paper often get lost, leading to disputes with customers.
3. **Overdue Receivables**: Shopkeepers forget payment commitments, creating severe working capital bottlenecks.
4. **Complex Accounting Apps**: Existing merchant apps require tedious multi-step form entry, barcode scans, or clunky UIs that merchants abandon during rush hours.

---

## 💡 The MVP & Core Demo Flow

### Core Flow:
```
Shopkeeper message (Voice / Text)
        │
        ▼
   AI extracts structured transaction (Customer, Amount, Type, Item, Due Date)
        │
        ▼
   Deterministic financial calculation updates customer balance
        │
        ▼
   Instant confirmation generated for shopkeeper & ledger logged
```

### Real-World Examples:
- **Credit Purchase**:
  - *Input:* `"Rahul took 2 packets of rice for 500, he'll pay Friday"`
  - *Output:* `"Recorded. Rahul now owes ₹500."`
- **Payment Settlement**:
  - *Input:* `"Rahul paid 300"`
  - *Output:* `"Payment recorded. Rahul's remaining balance is ₹200."`

---

## ☁️ Planned AWS Architecture
*Note: The planned AWS architecture will be introduced systematically in upcoming phases during the hackathon.*

```
┌─────────────────┐       HTTPS       ┌──────────────────────────────┐
│  React + Vite   │ ────────────────> │    Amazon API Gateway        │
│  Tailwind UI    │                   └──────────────┬───────────────┘
└─────────────────┘                                  │
                                                     ▼
                                      ┌──────────────────────────────┐
                                      │       AWS Lambda             │
                                      │   (Core Business Logic)      │
                                      └──────────────┬───────────────┘
                                                     │
                    ┌────────────────────────────────┼────────────────────────────────┐
                    │                                │                                │
                    ▼                                ▼                                ▼
     ┌──────────────────────────────┐ ┌──────────────────────────────┐ ┌──────────────────────────────┐
     │      Amazon Bedrock          │ │       Amazon DynamoDB        │ │     Amazon EventBridge       │
     │ (Natural Language Extraction)│ │   (Customers & Ledgers)      │ │   (Automated Due Reminders)  │
     └──────────────────────────────┘ └──────────────────────────────┘ └──────────────────────────────┘
```

- **Frontend/Demo**: React + TypeScript + Vite + Tailwind CSS
- **API**: Amazon API Gateway
- **Compute**: AWS Lambda (serverless microservices with zero idle cost)
- **AI / LLM**: Amazon Bedrock (structured JSON transaction extraction from voice/text)
- **Database**: Amazon DynamoDB (high throughput, single-digit millisecond latency for customer balances and transaction logs)
- **Automated Scheduling**: Amazon EventBridge + AWS Lambda (cron triggers for overdue reminders)
- **Storage** *(if needed)*: Amazon S3 (receipts and ledger exports)

---

## 🚀 Current Implementation Status (Phase 1)

| Phase | Milestone | Status |
|---|---|---|
| **Phase 1** | **Clean Frontend Foundation & Dashboard UI** | **COMPLETED** ✅ |
| Phase 2 | AWS API Gateway & DynamoDB Data Model | *Planned (Phase 2)* |
| Phase 3 | Amazon Bedrock Natural-Language Extraction | *Planned (Phase 3)* |
| Phase 4 | Full Frontend to AWS Backend Integration | *Planned (Phase 4)* |
| Phase 5 | Comprehensive Customer Khata Statements | *Planned (Phase 5)* |
| Phase 6 | Amazon EventBridge Automated Reminders | *Planned (Phase 6)* |
| Phase 7 | WhatsApp Cloud API Integration *(Bonus)* | *Planned (Phase 7)* |

> [!NOTE]
> In this initial Phase 1 foundation, UI components and workflows are driven by local mock data and deterministic client-side calculation rules. AWS services (Bedrock, DynamoDB, Lambda, EventBridge) are **not yet connected** and will be implemented in subsequent phases.

---

## 🛠️ Project Structure
```
src/
  components/
    dashboard/
      NaturalLanguageBar.tsx      # Voice & text quick entry with sample prompts
      StatCards.tsx               # Total credit, collections, active debtors, overdue count
      RecentTransactions.tsx      # Real-time transaction activity feed
      OverdueSection.tsx          # Actionable overdue accounts & reminder triggers
    customers/
      CustomerList.tsx            # Filterable directory with search & balance status
      CustomerLedgerModal.tsx     # Itemized khata sheet per customer
    transactions/
      TransactionList.tsx         # Filterable credit vs payment history
      AddTransactionModal.tsx     # Manual entry dialog fallback
    layout/
      Navbar.tsx                  # Kirana store branding & quick action bar
      TabNavigation.tsx           # Dashboard, Customers, and Transactions tabs
  pages/
    DashboardPage.tsx             # Main shopkeeper overview
    CustomersPage.tsx             # Customer directory view
    TransactionsPage.tsx          # Complete transaction logs
  services/
    ledgerService.ts              # Deterministic arithmetic & Phase 1 mock NLP parser
  hooks/
    useLedger.ts                  # State management with localStorage persistence
  types/
    index.ts                      # Domain models: Customer, Transaction, LedgerSummary
  utils/
    formatters.ts                 # INR (₹) currency formatting & date utilities
  data/
    mockData.ts                   # Realistic Indian kirana shopkeeper starter data
```

---

## 💻 Getting Started

### Prerequisites
- [Node.js](https://nodejs.org/) (v18 or v20+ recommended)
- `npm` (v9+)

### Installation
```bash
# Navigate to project directory
cd Lergerly-

# Install dependencies (if not already installed)
npm install
```

### Running the Development Server
```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser to explore the dashboard.

### Building for Production
```bash
npm run build
```

---

## 🔌 API Configuration (Frontend Service Layer)

The frontend includes a typed service client in `src/services/api.ts` for communicating with the backend.

- The API base URL is configured via the environment variable:
  ```env
  VITE_API_BASE_URL=
  ```
- Refer to `.env.example` for the environment template.
- **Current Status**: The base URL is currently unconfigured because Amazon API Gateway has not yet been deployed. The UI continues to run on local state and mock data until Phase 4 (Frontend-Backend Integration).
