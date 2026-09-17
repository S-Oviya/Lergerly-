import React, { useState } from 'react';
import { Customer } from '../../types';
import { formatCurrency, getDueDateStatus } from '../../utils/formatters';
import { AlertCircle, Bell, Check, Phone, ChevronRight } from 'lucide-react';

interface OverdueSectionProps {
  customers: Customer[];
  onSelectCustomer: (customer: Customer) => void;
}

export const OverdueSection: React.FC<OverdueSectionProps> = ({
  customers,
  onSelectCustomer,
}) => {
  const [remindedIds, setRemindedIds] = useState<Record<string, boolean>>({});

  const overdueCustomers = customers.filter(
    (c) => c.balance > 0 && c.dueDate && getDueDateStatus(c.dueDate).isOverdue
  );

  const handleSendReminder = (e: React.MouseEvent, customerId: string) => {
    e.stopPropagation();
    setRemindedIds((prev) => ({ ...prev, [customerId]: true }));
    setTimeout(() => {
      setRemindedIds((prev) => ({ ...prev, [customerId]: false }));
    }, 4000);
  };

  if (overdueCustomers.length === 0) {
    return (
      <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-xs">
        <div className="flex items-center gap-2 mb-2">
          <AlertCircle className="w-4 h-4 text-emerald-600" />
          <h3 className="text-sm font-bold text-slate-900">Overdue Khata Reminders</h3>
        </div>
        <p className="text-xs text-slate-500">
          All accounts are on track! No customers have overdue balances right now.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
          <h3 className="text-sm font-bold text-slate-900">
            Overdue Khata Reminders ({overdueCustomers.length})
          </h3>
        </div>
        <span className="text-[11px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200/60">
          Action Recommended
        </span>
      </div>

      <div className="divide-y divide-slate-100">
        {overdueCustomers.map((customer) => {
          const status = getDueDateStatus(customer.dueDate);
          const isSent = remindedIds[customer.id];

          return (
            <div
              key={customer.id}
              onClick={() => onSelectCustomer(customer)}
              className="px-5 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/80 transition-colors cursor-pointer"
            >
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-800 font-bold flex items-center justify-center shrink-0 text-xs">
                  {customer.name.slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-slate-900">{customer.name}</span>
                    <span className="text-[11px] font-medium text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full">
                      {status.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
                    <span className="flex items-center gap-1">
                      <Phone className="w-3 h-3 text-slate-400" />
                      {customer.phone}
                    </span>
                    {customer.notes && (
                      <span className="hidden md:inline truncate max-w-xs text-slate-400">
                        • {customer.notes}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
                <div className="text-right">
                  <span className="block text-[10px] uppercase font-semibold text-slate-400">
                    Overdue Amount
                  </span>
                  <span className="text-sm font-bold text-rose-700">
                    {formatCurrency(customer.balance)}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={(e) => handleSendReminder(e, customer.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
                    isSent
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 hover:bg-amber-200 text-amber-900'
                  }`}
                  title="Send automated reminder (Simulated EventBridge flow)"
                >
                  {isSent ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Reminder Sent</span>
                    </>
                  ) : (
                    <>
                      <Bell className="w-3.5 h-3.5 text-amber-700" />
                      <span>Remind</span>
                    </>
                  )}
                </button>
                <ChevronRight className="w-4 h-4 text-slate-300 hidden sm:block" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
