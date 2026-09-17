import React from 'react';
import { Transaction } from '../../types';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { ArrowUpRight, ArrowDownLeft, Clock, ShoppingBag } from 'lucide-react';

interface RecentTransactionsProps {
  transactions: Transaction[];
  onViewAll: () => void;
}

export const RecentTransactions: React.FC<RecentTransactionsProps> = ({
  transactions,
  onViewAll,
}) => {
  const recent = transactions.slice(0, 5);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Recent Transactions</h3>
          <p className="text-xs text-slate-500">Live ledger activity feed</p>
        </div>
        <button
          onClick={onViewAll}
          className="text-xs font-semibold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
        >
          <span>View All</span>
          <ArrowUpRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {recent.length === 0 ? (
        <div className="p-8 text-center text-slate-400 text-xs">
          No transactions recorded yet.
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {recent.map((tx) => {
            const isCredit = tx.type === 'CREDIT';

            return (
              <div
                key={tx.id}
                className="px-5 py-3.5 flex items-center justify-between gap-3 hover:bg-slate-50/70 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                      isCredit
                        ? 'bg-rose-50 text-rose-600'
                        : 'bg-emerald-50 text-emerald-600'
                    }`}
                  >
                    {isCredit ? (
                      <ArrowUpRight className="w-4 h-4" />
                    ) : (
                      <ArrowDownLeft className="w-4 h-4" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-slate-900">
                        {tx.customerName}
                      </span>
                      <span
                        className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                          isCredit
                            ? 'bg-rose-100/70 text-rose-700'
                            : 'bg-emerald-100/70 text-emerald-700'
                        }`}
                      >
                        {isCredit ? 'Credit (Udhar)' : 'Payment Received'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
                      {tx.itemsNote && (
                        <span className="flex items-center gap-1 text-slate-600">
                          <ShoppingBag className="w-3 h-3 text-slate-400" />
                          {tx.itemsNote}
                        </span>
                      )}
                      <span className="text-slate-300">•</span>
                      <span className="flex items-center gap-1 text-slate-400">
                        <Clock className="w-3 h-3" />
                        {formatDate(tx.timestamp)}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <span
                    className={`text-sm font-bold ${
                      isCredit ? 'text-rose-600' : 'text-emerald-600'
                    }`}
                  >
                    {isCredit ? '+' : '-'}
                    {formatCurrency(tx.amount)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
