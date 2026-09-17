import React, { useState } from 'react';
import { Transaction } from '../../types';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { Search, ArrowUpRight, ArrowDownLeft, Calendar, ShoppingBag, Plus } from 'lucide-react';

interface TransactionListProps {
  transactions: Transaction[];
  onOpenAddModal: () => void;
}

export const TransactionList: React.FC<TransactionListProps> = ({
  transactions,
  onOpenAddModal,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'CREDIT' | 'PAYMENT'>('ALL');

  const filtered = transactions.filter((t) => {
    const matchesSearch =
      t.customerName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (t.itemsNote && t.itemsNote.toLowerCase().includes(searchTerm.toLowerCase()));

    if (!matchesSearch) return false;
    if (typeFilter === 'CREDIT') return t.type === 'CREDIT';
    if (typeFilter === 'PAYMENT') return t.type === 'PAYMENT';
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Top Filter Bar */}
      <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-xs flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by customer or item..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-end">
          <div className="flex bg-slate-100 p-1 rounded-lg text-xs font-medium text-slate-600">
            <button
              onClick={() => setTypeFilter('ALL')}
              className={`px-3 py-1 rounded-md transition-colors ${
                typeFilter === 'ALL'
                  ? 'bg-white text-slate-900 shadow-xs font-semibold'
                  : 'hover:text-slate-900'
              }`}
            >
              All ({transactions.length})
            </button>
            <button
              onClick={() => setTypeFilter('CREDIT')}
              className={`px-3 py-1 rounded-md transition-colors ${
                typeFilter === 'CREDIT'
                  ? 'bg-white text-rose-700 shadow-xs font-semibold'
                  : 'hover:text-slate-900'
              }`}
            >
              Credit ({transactions.filter((t) => t.type === 'CREDIT').length})
            </button>
            <button
              onClick={() => setTypeFilter('PAYMENT')}
              className={`px-3 py-1 rounded-md transition-colors ${
                typeFilter === 'PAYMENT'
                  ? 'bg-white text-emerald-700 shadow-xs font-semibold'
                  : 'hover:text-slate-900'
              }`}
            >
              Payments ({transactions.filter((t) => t.type === 'PAYMENT').length})
            </button>
          </div>

          <button
            onClick={onOpenAddModal}
            className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors shrink-0"
          >
            <Plus className="w-4 h-4" />
            <span>New Entry</span>
          </button>
        </div>
      </div>

      {/* Transactions Feed */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-sm">
            No transactions match your search.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {filtered.map((tx) => {
              const isCredit = tx.type === 'CREDIT';

              return (
                <div
                  key={tx.id}
                  className="p-4 sm:p-5 flex items-center justify-between gap-4 hover:bg-slate-50/70 transition-colors"
                >
                  <div className="flex items-center gap-3.5">
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                        isCredit
                          ? 'bg-rose-50 text-rose-600 border border-rose-100'
                          : 'bg-emerald-50 text-emerald-600 border border-emerald-100'
                      }`}
                    >
                      {isCredit ? (
                        <ArrowUpRight className="w-5 h-5" />
                      ) : (
                        <ArrowDownLeft className="w-5 h-5" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm sm:text-base text-slate-900">
                          {tx.customerName}
                        </span>
                        <span
                          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                            isCredit
                              ? 'bg-rose-100 text-rose-700'
                              : 'bg-emerald-100 text-emerald-700'
                          }`}
                        >
                          {isCredit ? 'Credit Given (Udhar)' : 'Payment Received'}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 mt-1">
                        {tx.itemsNote && (
                          <span className="flex items-center gap-1 text-slate-600">
                            <ShoppingBag className="w-3.5 h-3.5 text-slate-400" />
                            {tx.itemsNote}
                          </span>
                        )}
                        <span className="text-slate-300">•</span>
                        <span>{formatDate(tx.timestamp)}</span>
                        {tx.dueDate && (
                          <>
                            <span className="text-slate-300">•</span>
                            <span className="flex items-center gap-1 text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                              <Calendar className="w-3 h-3" />
                              Promised: {formatDate(tx.dueDate)}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <span
                      className={`text-base sm:text-lg font-bold ${
                        isCredit ? 'text-rose-600' : 'text-emerald-600'
                      }`}
                    >
                      {isCredit ? '+' : '-'}
                      {formatCurrency(tx.amount)}
                    </span>
                    <span className="block text-[10px] uppercase font-medium text-slate-400">
                      {isCredit ? 'Added to debt' : 'Deducted'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
