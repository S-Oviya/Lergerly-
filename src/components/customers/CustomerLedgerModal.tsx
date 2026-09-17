import React, { useState } from 'react';
import { Customer, Transaction, TransactionType } from '../../types';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { X, ArrowUpRight, ArrowDownLeft, Phone, Calendar, ShoppingBag, Plus, IndianRupee } from 'lucide-react';

interface CustomerLedgerModalProps {
  customer: Customer | null;
  transactions: Transaction[];
  onClose: () => void;
  onAddTransaction: (data: {
    customerName: string;
    type: TransactionType;
    amount: number;
    itemsNote?: string;
  }) => void;
}

export const CustomerLedgerModal: React.FC<CustomerLedgerModalProps> = ({
  customer,
  transactions,
  onClose,
  onAddTransaction,
}) => {
  const [quickType, setQuickType] = useState<TransactionType>('PAYMENT');
  const [quickAmount, setQuickAmount] = useState('');
  const [quickNote, setQuickNote] = useState('');

  if (!customer) return null;

  const customerTxs = transactions.filter((t) => t.customerId === customer.id);

  const handleQuickSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const amt = parseFloat(quickAmount);
    if (isNaN(amt) || amt <= 0) return;

    onAddTransaction({
      customerName: customer.name,
      type: quickType,
      amount: amt,
      itemsNote: quickNote || (quickType === 'PAYMENT' ? 'Payment settlement' : 'Credit purchase'),
    });

    setQuickAmount('');
    setQuickNote('');
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl max-w-2xl w-full overflow-hidden shadow-2xl border border-slate-200">
        {/* Header with Balance Badge */}
        <div className="bg-gradient-to-r from-slate-900 to-slate-800 text-white p-5 sm:p-6">
          <div className="flex items-start justify-between">
            <div>
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
                Customer Khata Sheet
              </span>
              <h3 className="text-xl font-bold text-white mt-1">{customer.name}</h3>
              <div className="flex items-center gap-3 text-xs text-slate-300 mt-1">
                <span className="flex items-center gap-1">
                  <Phone className="w-3.5 h-3.5 text-slate-400" />
                  {customer.phone}
                </span>
                {customer.dueDate && (
                  <span className="flex items-center gap-1 text-amber-300">
                    <Calendar className="w-3.5 h-3.5" />
                    Due: {formatDate(customer.dueDate)}
                  </span>
                )}
              </div>
            </div>

            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white p-1 rounded-lg bg-slate-800/80 hover:bg-slate-700 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Balance Bar */}
          <div className="mt-5 p-3.5 bg-slate-800/80 rounded-xl border border-slate-700/80 flex items-center justify-between">
            <div>
              <span className="text-[11px] uppercase font-semibold text-slate-400 block">
                Current Outstanding Balance (Net)
              </span>
              <p className="text-2xl font-black text-white">
                {formatCurrency(customer.balance)}
              </p>
            </div>
            <div className="text-right">
              <span
                className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                  customer.balance > 0
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                }`}
              >
                {customer.balance > 0 ? 'Customer Owes' : 'Account Settled'}
              </span>
            </div>
          </div>
        </div>

        {/* Quick Entry Form for this customer */}
        <div className="bg-slate-50 p-4 border-b border-slate-200">
          <form onSubmit={handleQuickSubmit} className="flex flex-col sm:flex-row gap-2 items-center">
            <div className="flex rounded-lg overflow-hidden border border-slate-300 shrink-0">
              <button
                type="button"
                onClick={() => setQuickType('PAYMENT')}
                className={`px-3 py-1.5 text-xs font-bold transition-colors ${
                  quickType === 'PAYMENT'
                    ? 'bg-emerald-600 text-white'
                    : 'bg-white text-slate-700 hover:bg-slate-100'
                }`}
              >
                Receive Payment
              </button>
              <button
                type="button"
                onClick={() => setQuickType('CREDIT')}
                className={`px-3 py-1.5 text-xs font-bold transition-colors ${
                  quickType === 'CREDIT'
                    ? 'bg-rose-600 text-white'
                    : 'bg-white text-slate-700 hover:bg-slate-100'
                }`}
              >
                Give Credit (Udhar)
              </button>
            </div>

            <div className="relative w-full sm:w-32">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-400">₹</span>
              <input
                type="number"
                placeholder="Amount"
                value={quickAmount}
                onChange={(e) => setQuickAmount(e.target.value)}
                min="1"
                className="w-full pl-6 pr-2 py-1.5 text-xs font-medium border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            <input
              type="text"
              placeholder="Items or note (e.g. 5kg wheat)"
              value={quickNote}
              onChange={(e) => setQuickNote(e.target.value)}
              className="w-full sm:flex-1 px-3 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />

            <button
              type="submit"
              disabled={!quickAmount}
              className="w-full sm:w-auto px-4 py-1.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center justify-center gap-1 shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Record</span>
            </button>
          </form>
        </div>

        {/* Khata Transactions History */}
        <div className="max-h-80 overflow-y-auto divide-y divide-slate-100">
          {customerTxs.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-xs">
              No entries recorded yet for this customer.
            </div>
          ) : (
            customerTxs.map((tx) => {
              const isCredit = tx.type === 'CREDIT';
              return (
                <div
                  key={tx.id}
                  className="p-4 flex items-center justify-between hover:bg-slate-50/80 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
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
                        <span className="font-semibold text-xs text-slate-900">
                          {isCredit ? 'Credit (Goods Taken)' : 'Payment Settled'}
                        </span>
                        {tx.dueDate && (
                          <span className="text-[10px] text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                            Due: {formatDate(tx.dueDate)}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
                        {tx.itemsNote && (
                          <span className="flex items-center gap-1 text-slate-600">
                            <ShoppingBag className="w-3 h-3 text-slate-400" />
                            {tx.itemsNote}
                          </span>
                        )}
                        <span className="text-slate-300">•</span>
                        <span className="text-slate-400">{formatDate(tx.timestamp)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="text-right">
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
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-xs font-semibold transition-colors"
          >
            Close Khata Sheet
          </button>
        </div>
      </div>
    </div>
  );
};
