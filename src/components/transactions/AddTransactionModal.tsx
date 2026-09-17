import React, { useState } from 'react';
import { Customer, TransactionType } from '../../types';
import { X, Check } from 'lucide-react';

interface AddTransactionModalProps {
  isOpen: boolean;
  onClose: () => void;
  existingCustomers: Customer[];
  onAddTransaction: (data: {
    customerName: string;
    phone?: string;
    type: TransactionType;
    amount: number;
    itemsNote?: string;
    dueDate?: string;
  }) => void;
}

export const AddTransactionModal: React.FC<AddTransactionModalProps> = ({
  isOpen,
  onClose,
  existingCustomers,
  onAddTransaction,
}) => {
  const [customerName, setCustomerName] = useState('');
  const [phone, setPhone] = useState('');
  const [type, setType] = useState<TransactionType>('CREDIT');
  const [amount, setAmount] = useState('');
  const [itemsNote, setItemsNote] = useState('');
  const [dueDate, setDueDate] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const parsedAmount = parseFloat(amount);
    if (!customerName.trim() || isNaN(parsedAmount) || parsedAmount <= 0) {
      return;
    }

    onAddTransaction({
      customerName: customerName.trim(),
      phone: phone.trim() || undefined,
      type,
      amount: parsedAmount,
      itemsNote: itemsNote.trim() || undefined,
      dueDate: dueDate ? new Date(dueDate).toISOString() : undefined,
    });

    onClose();
  };

  const handleSelectExisting = (c: Customer) => {
    setCustomerName(c.name);
    setPhone(c.phone);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl max-w-lg w-full overflow-hidden shadow-2xl border border-slate-200">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">Add Khata Transaction</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Type Selector Tabs */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Transaction Type
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setType('CREDIT')}
                className={`py-2 px-3 text-xs font-bold rounded-lg border text-center transition-all ${
                  type === 'CREDIT'
                    ? 'bg-rose-50 border-rose-400 text-rose-700 ring-2 ring-rose-200'
                    : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                + Give Credit (Udhar)
              </button>
              <button
                type="button"
                onClick={() => setType('PAYMENT')}
                className={`py-2 px-3 text-xs font-bold rounded-lg border text-center transition-all ${
                  type === 'PAYMENT'
                    ? 'bg-emerald-50 border-emerald-400 text-emerald-700 ring-2 ring-emerald-200'
                    : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                - Receive Payment
              </button>
            </div>
          </div>

          {/* Customer Name */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Customer Name *
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Rahul Sharma"
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            {/* Quick customer picker pills */}
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <span className="text-[10px] text-slate-400 self-center">Existing:</span>
              {existingCustomers.slice(0, 4).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => handleSelectExisting(c)}
                  className="text-[11px] px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700"
                >
                  {c.name.split(' ')[0]}
                </button>
              ))}
            </div>
          </div>

          {/* Phone */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Phone Number (Optional)
            </label>
            <input
              type="tel"
              placeholder="+91 98765 43210"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* Amount */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Amount (₹) *
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-bold text-slate-400">
                ₹
              </span>
              <input
                type="number"
                required
                min="1"
                placeholder="500"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full pl-8 pr-3 py-2 text-sm font-semibold border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>
          </div>

          {/* Items / Note */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Items / Note
            </label>
            <input
              type="text"
              placeholder="e.g. 2 packets of rice, mustard oil"
              value={itemsNote}
              onChange={(e) => setItemsNote(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* Due Date (If Credit) */}
          {type === 'CREDIT' && (
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Payment Promised Date (Due Date)
              </label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>
          )}

          <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
            >
              <Check className="w-4 h-4" />
              <span>Save Entry</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
