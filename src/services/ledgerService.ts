import { Customer, Transaction, LedgerSummary, NLParseResult, TransactionType } from '../types';
import { isOverdue } from '../utils/formatters';

export class LedgerService {
  /**
   * Deterministically calculates customer balance from list of transactions.
   * balance = sum(CREDIT) - sum(PAYMENT)
   */
  static calculateCustomerBalance(transactions: Transaction[], customerId: string): number {
    return transactions
      .filter((t) => t.customerId === customerId)
      .reduce((acc, curr) => {
        return curr.type === 'CREDIT' ? acc + curr.amount : acc - curr.amount;
      }, 0);
  }

  /**
   * Calculates high-level shopkeeper ledger KPIs.
   */
  static calculateSummary(customers: Customer[], transactions: Transaction[]): LedgerSummary {
    const totalCreditOwed = customers.reduce((sum, c) => (c.balance > 0 ? sum + c.balance : sum), 0);
    
    // Today anchor: 2026-09-17
    const todayStr = '2026-09-17';
    const totalCollectedToday = transactions
      .filter((t) => t.type === 'PAYMENT' && t.timestamp.startsWith(todayStr))
      .reduce((sum, t) => sum + t.amount, 0);

    const activeDebtorsCount = customers.filter((c) => c.balance > 0).length;
    const overdueCount = customers.filter((c) => c.balance > 0 && isOverdue(c.dueDate)).length;

    return {
      totalCreditOwed,
      totalCollectedToday,
      activeDebtorsCount,
      overdueCount,
    };
  }

  /**
   * Mock natural language parser for Phase 1 frontend demonstration.
   * In Phase 3, this will be replaced by Amazon Bedrock extraction via AWS Lambda.
   */
  static parseNaturalLanguageInput(
    input: string,
    existingCustomers: Customer[]
  ): NLParseResult | null {
    const cleaned = input.trim();
    if (!cleaned) return null;

    const lower = cleaned.toLowerCase();

    // 1. Detect transaction type
    const isPayment = /\b(paid|gave|settled|cleared|recvd|received)\b/i.test(cleaned);
    const type: TransactionType = isPayment ? 'PAYMENT' : 'CREDIT';

    // 2. Extract numeric amount
    // Matches patterns like "500", "for 500", "paid 300", "rs 500", "500 rs", "₹500"
    const amountMatch = cleaned.match(/(?:for|paid|of|₹|rs\.?|inr)?\s*([0-9]+(?:,[0-9]+)?(?:\.[0-9]{1,2})?)(?:\s*(?:rs|rupees|inr))?/i);
    let amount = 0;
    if (amountMatch) {
      // Find the first integer/float that looks like money
      const allNumbers = cleaned.match(/\b\d+(\.\d{1,2})?\b/g);
      if (allNumbers && allNumbers.length > 0) {
        // usually the largest or trailing number in phrasing is the amount
        // if multiple numbers (e.g. "2 packets for 500"), pick 500
        const parsed = allNumbers.map(n => parseFloat(n));
        amount = parsed.length > 1 ? Math.max(...parsed) : parsed[0];
      }
    }

    if (!amount || isNaN(amount)) {
      amount = 100; // fallback if no amount detected
    }

    // 3. Match or infer customer name
    let matchedCustomer = existingCustomers.find((c) =>
      lower.includes(c.name.toLowerCase().split(' ')[0])
    );

    let customerName = matchedCustomer?.name || '';
    if (!customerName) {
      // Try extracting first word or capitalize
      const words = cleaned.split(/\s+/);
      if (words.length > 0) {
        customerName = words[0].charAt(0).toUpperCase() + words[0].slice(1).toLowerCase();
      } else {
        customerName = 'Walk-in Customer';
      }
    }

    // 4. Extract item/note description
    let itemsNote = '';
    if (type === 'CREDIT') {
      const itemMatch = cleaned.match(/(?:took|bought|got|purchased)\s+(.*?)(?:\s+for|\s+on|\s+he'll|\s+due|\.|$)/i);
      if (itemMatch && itemMatch[1]) {
        itemsNote = itemMatch[1].trim();
      } else {
        itemsNote = 'Store goods on credit';
      }
    } else {
      itemsNote = 'Credit account payment';
    }

    // 5. Inferred Due Date if mentioned
    let dueDate: string | undefined;
    if (lower.includes('friday')) {
      dueDate = '2026-09-19T23:59:59Z';
    } else if (lower.includes('tomorrow')) {
      dueDate = '2026-09-18T20:00:00Z';
    } else if (lower.includes('sunday')) {
      dueDate = '2026-09-20T20:00:00Z';
    } else if (type === 'CREDIT') {
      // Default to 7 days credit
      dueDate = '2026-09-24T20:00:00Z';
    }

    // 6. Deterministic balance calculation
    const currentBalance = matchedCustomer ? matchedCustomer.balance : 0;
    const customerBalanceAfter =
      type === 'CREDIT'
        ? currentBalance + amount
        : Math.max(0, currentBalance - amount);

    // 7. Standardized confirmation message
    const firstName = customerName.split(' ')[0];
    let confirmationText = '';
    if (type === 'CREDIT') {
      confirmationText = `Recorded. ${firstName} now owes ₹${customerBalanceAfter}.`;
    } else {
      confirmationText = `Payment recorded. ${firstName}'s remaining balance is ₹${customerBalanceAfter}.`;
    }

    return {
      success: true,
      rawInput: input,
      confirmationText,
      customerName,
      type,
      amount,
      itemsNote,
      dueDate,
      customerBalanceAfter,
    };
  }
}
