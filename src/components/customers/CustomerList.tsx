import React, { useState } from 'react';
import { Customer } from '../../types';
import { formatCurrency, formatDate, getDueDateStatus } from '../../utils/formatters';
import { Search, Phone, BookOpen, AlertCircle, CheckCircle, Plus } from 'lucide-react';

interface CustomerListProps {
  customers: Customer[];
  onSelectCustomer: (customer: Customer) => void;
  onOpenAddModal: () => void;
}

export const CustomerList: React.FC<CustomerListProps> = ({
  customers,
  onSelectCustomer,
  onOpenAddModal,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filter, setFilter] = useState<'all' | 'balance' | 'cleared'>('all');

  const filteredCustomers = customers.filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.phone.includes(searchTerm);

    if (!matchesSearch) return false;

    if (filter === 'balance') return c.balance > 0;
    if (filter === 'cleared') return c.balance === 0;
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Top Controls: Search & Filter Tabs */}
      <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-xs flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search customer by name or phone..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-end">
          <div className="flex bg-slate-100 p-1 rounded-lg text-xs font-medium text-slate-600">
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1 rounded-md transition-colors ${
                filter === 'all' ? 'bg-white text-slate-900 shadow-xs font-semibold' : 'hover:text-slate-900'
              }`}
            >
              All ({customers.length})
            </button>
            <button
              onClick={() => setFilter('balance')}
              className={`px-3 py-1 rounded-md transition-colors ${
                filter === 'balance' ? 'bg-white text-slate-900 shadow-xs font-semibold' : 'hover:text-slate-900'
              }`}
            >
              With Balance ({customers.filter((c) => c.balance > 0).length})
            </button>
            <button
              onClick={() => setFilter('cleared')}
              className={`px-3 py-1 rounded-md transition-colors ${
                filter === 'cleared' ? 'bg-white text-slate-900 shadow-xs font-semibold' : 'hover:text-slate-900'
              }`}
            >
              Cleared ({customers.filter((c) => c.balance === 0).length})
            </button>
          </div>

          <button
            onClick={onOpenAddModal}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Add Customer</span>
          </button>
        </div>
      </div>

      {/* Customer Cards Grid / Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        {filteredCustomers.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-slate-500 text-sm">No customers match your search.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {filteredCustomers.map((customer) => {
              const status = getDueDateStatus(customer.dueDate);
              const hasBalance = customer.balance > 0;

              return (
                <div
                  key={customer.id}
                  onClick={() => onSelectCustomer(customer)}
                  className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50 transition-colors cursor-pointer"
                >
                  <div className="flex items-start gap-3.5">
                    <div className="w-10 h-10 rounded-full bg-slate-100 border border-slate-200 text-slate-700 font-bold flex items-center justify-center shrink-0 text-sm">
                      {customer.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="font-semibold text-sm sm:text-base text-slate-900">
                          {customer.name}
                        </h4>
                        {hasBalance && status.isOverdue && (
                          <span className="text-[10px] font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200/50">
                            {status.label}
                          </span>
                        )}
                        {!hasBalance && (
                          <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" />
                            Settled
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 mt-1">
                        <span className="flex items-center gap-1">
                          <Phone className="w-3 h-3 text-slate-400" />
                          {customer.phone}
                        </span>
                        {customer.notes && (
                          <span className="text-slate-400 hidden md:inline">
                            • {customer.notes}
                          </span>
                        )}
                        <span className="text-slate-400">
                          • Last active: {formatDate(customer.lastTransactionDate)}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between sm:justify-end gap-4 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-100">
                    <div className="text-left sm:text-right">
                      <span className="block text-[10px] uppercase font-semibold text-slate-400">
                        Total Khata Balance
                      </span>
                      <span
                        className={`text-base sm:text-lg font-bold ${
                          hasBalance ? 'text-rose-700' : 'text-emerald-600'
                        }`}
                      >
                        {formatCurrency(customer.balance)}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectCustomer(customer);
                      }}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200/60 flex items-center gap-1.5 transition-colors"
                    >
                      <BookOpen className="w-3.5 h-3.5" />
                      <span>View Khata</span>
                    </button>
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
