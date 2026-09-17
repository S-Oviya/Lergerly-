import React from 'react';
import { Customer, LedgerSummary, NLParseResult, Transaction } from '../types';
import { StatCards } from '../components/dashboard/StatCards';
import { NaturalLanguageBar } from '../components/dashboard/NaturalLanguageBar';
import { OverdueSection } from '../components/dashboard/OverdueSection';
import { RecentTransactions } from '../components/dashboard/RecentTransactions';

interface DashboardPageProps {
  summary: LedgerSummary;
  customers: Customer[];
  transactions: Transaction[];
  latestNLResult: NLParseResult | null;
  onProcessCommand: (input: string) => NLParseResult | null;
  onClearResult: () => void;
  onSelectCustomer: (customer: Customer) => void;
  onViewAllTransactions: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  summary,
  customers,
  transactions,
  latestNLResult,
  onProcessCommand,
  onClearResult,
  onSelectCustomer,
  onViewAllTransactions,
}) => {
  return (
    <div className="space-y-6">
      {/* 1. Natural Language Shopkeeper Command Bar */}
      <NaturalLanguageBar
        onProcessCommand={onProcessCommand}
        latestResult={latestNLResult}
        onClearResult={onClearResult}
      />

      {/* 2. Ledger KPI Summary Cards */}
      <StatCards summary={summary} />

      {/* 3. Main Dashboard 2-Column Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Recent Transactions */}
        <div className="lg:col-span-2">
          <RecentTransactions
            transactions={transactions}
            onViewAll={onViewAllTransactions}
          />
        </div>

        {/* Right 1 Col: Overdue Accounts & Actionable Reminders */}
        <div className="lg:col-span-1">
          <OverdueSection
            customers={customers}
            onSelectCustomer={onSelectCustomer}
          />
        </div>
      </div>
    </div>
  );
};
