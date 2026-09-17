import { useState, useEffect } from 'react';
import { Customer, Transaction, LedgerSummary, NLParseResult, TransactionType } from '../types';
import { INITIAL_CUSTOMERS, INITIAL_TRANSACTIONS } from '../data/mockData';
import { LedgerService } from '../services/ledgerService';

const STORAGE_CUSTOMERS_KEY = 'ledgerly_customers_v1';
const STORAGE_TRANSACTIONS_KEY = 'ledgerly_transactions_v1';

export function useLedger() {
  const [customers, setCustomers] = useState<Customer[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_CUSTOMERS_KEY);
      return saved ? JSON.parse(saved) : INITIAL_CUSTOMERS;
    } catch {
      return INITIAL_CUSTOMERS;
    }
  });

  const [transactions, setTransactions] = useState<Transaction[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_TRANSACTIONS_KEY);
      return saved ? JSON.parse(saved) : INITIAL_TRANSACTIONS;
    } catch {
      return INITIAL_TRANSACTIONS;
    }
  });

  const [latestNLResult, setLatestNLResult] = useState<NLParseResult | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_CUSTOMERS_KEY, JSON.stringify(customers));
      localStorage.setItem(STORAGE_TRANSACTIONS_KEY, JSON.stringify(transactions));
    } catch (e) {
      console.warn('Failed to save to localStorage:', e);
    }
  }, [customers, transactions]);

  const summary: LedgerSummary = LedgerService.calculateSummary(customers, transactions);

  /**
   * Commit a transaction and update the customer's balance deterministically.
   */
  const addTransaction = (data: {
    customerName: string;
    phone?: string;
    type: TransactionType;
    amount: number;
    itemsNote?: string;
    dueDate?: string;
  }) => {
    const timestamp = new Date().toISOString();
    const cleanCustomerName = data.customerName.trim();

    // Check if customer exists (case-insensitive name match)
    let customer = customers.find(
      (c) => c.name.toLowerCase() === cleanCustomerName.toLowerCase()
    );

    let customerId = customer?.id;

    let updatedCustomers = [...customers];

    if (!customer) {
      // Create new customer
      customerId = `cust-${Date.now()}`;
      customer = {
        id: customerId,
        name: cleanCustomerName,
        phone: data.phone || '+91 98000 00000',
        balance: 0,
        lastTransactionDate: timestamp,
        dueDate: data.dueDate,
        notes: 'Created via Ledgerly',
      };
      updatedCustomers.push(customer);
    }

    // Deterministic balance calculation
    const balanceChange = data.type === 'CREDIT' ? data.amount : -data.amount;
    const newBalance = Math.max(0, (customer.balance || 0) + balanceChange);

    updatedCustomers = updatedCustomers.map((c) => {
      if (c.id === customerId) {
        return {
          ...c,
          balance: newBalance,
          lastTransactionDate: timestamp,
          ...(data.dueDate ? { dueDate: data.dueDate } : {}),
        };
      }
      return c;
    });

    const newTx: Transaction = {
      id: `tx-${Date.now()}`,
      customerId: customerId!,
      customerName: customer.name,
      type: data.type,
      amount: data.amount,
      itemsNote: data.itemsNote,
      timestamp,
      dueDate: data.dueDate,
    };

    setCustomers(updatedCustomers);
    setTransactions([newTx, ...transactions]);

    return { transaction: newTx, newBalance };
  };

  /**
   * Process Natural Language command, e.g. "Rahul took 2 packets of rice for 500"
   */
  const processNaturalLanguage = (input: string): NLParseResult | null => {
    const parsed = LedgerService.parseNaturalLanguageInput(input, customers);
    if (!parsed) return null;

    addTransaction({
      customerName: parsed.customerName,
      type: parsed.type,
      amount: parsed.amount,
      itemsNote: parsed.itemsNote,
      dueDate: parsed.dueDate,
    });

    setLatestNLResult(parsed);
    return parsed;
  };

  const clearLatestNLResult = () => setLatestNLResult(null);

  const resetData = () => {
    localStorage.removeItem(STORAGE_CUSTOMERS_KEY);
    localStorage.removeItem(STORAGE_TRANSACTIONS_KEY);
    setCustomers(INITIAL_CUSTOMERS);
    setTransactions(INITIAL_TRANSACTIONS);
    setLatestNLResult(null);
  };

  return {
    customers,
    transactions,
    summary,
    latestNLResult,
    addTransaction,
    processNaturalLanguage,
    clearLatestNLResult,
    resetData,
  };
}
