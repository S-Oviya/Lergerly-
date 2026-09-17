import React from 'react';
import { Transaction } from '../types';
import { TransactionList } from '../components/transactions/TransactionList';

interface TransactionsPageProps {
  transactions: Transaction[];
  onOpenAddModal: () => void;
}

export const TransactionsPage: React.FC<TransactionsPageProps> = ({
  transactions,
  onOpenAddModal,
}) => {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-slate-900 tracking-tight">All Transactions</h2>
        <p className="text-xs text-slate-500">
          Comprehensive log of credit goods taken and payments collected.
        </p>
      </div>

      <TransactionList
        transactions={transactions}
        onOpenAddModal={onOpenAddModal}
      />
    </div>
  );
};
