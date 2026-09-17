export type TransactionType = 'CREDIT' | 'PAYMENT';

export interface Transaction {
  id: string;
  customerId: string;
  customerName: string;
  type: TransactionType;
  amount: number;
  itemsNote?: string;
  timestamp: string;
  dueDate?: string;
}

export interface Customer {
  id: string;
  name: string;
  phone: string;
  balance: number; // positive = owes money to shopkeeper, 0 = settled
  lastTransactionDate: string;
  dueDate?: string;
  notes?: string;
}

export interface LedgerSummary {
  totalCreditOwed: number;
  totalCollectedToday: number;
  activeDebtorsCount: number;
  overdueCount: number;
}

export interface NLParseResult {
  success: boolean;
  rawInput: string;
  confirmationText: string;
  customerName: string;
  type: TransactionType;
  amount: number;
  itemsNote?: string;
  dueDate?: string;
  customerBalanceAfter: number;
}

export type TabType = 'dashboard' | 'customers' | 'transactions';
