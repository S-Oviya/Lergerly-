import React from 'react';
import { LedgerSummary } from '../../types';
import { formatCurrency } from '../../utils/formatters';
import { IndianRupee, ArrowDownCircle, Users, AlertTriangle } from 'lucide-react';

interface StatCardsProps {
  summary: LedgerSummary;
}

export const StatCards: React.FC<StatCardsProps> = ({ summary }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Total Credit Owed */}
      <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-xs">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Total Credit Given (Udhar)
          </span>
          <div className="w-8 h-8 rounded-lg bg-rose-50 flex items-center justify-center text-rose-600">
            <IndianRupee className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline justify-between">
          <p className="text-2xl font-bold text-slate-900">
            {formatCurrency(summary.totalCreditOwed)}
          </p>
          <span className="text-xs font-medium text-rose-700 bg-rose-50 px-2 py-0.5 rounded-md">
            To Collect
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">Across all active customer accounts</p>
      </div>

      {/* Total Collected Today */}
      <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-xs">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Collected Today
          </span>
          <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center text-emerald-600">
            <ArrowDownCircle className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline justify-between">
          <p className="text-2xl font-bold text-emerald-700">
            {formatCurrency(summary.totalCollectedToday)}
          </p>
          <span className="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md">
            Received
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">Cash & UPI settlements recorded</p>
      </div>

      {/* Active Debtors */}
      <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-xs">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Active Debtors
          </span>
          <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center text-blue-600">
            <Users className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline justify-between">
          <p className="text-2xl font-bold text-slate-900">
            {summary.activeDebtorsCount}
          </p>
          <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md">
            Customers
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">Currently carry an open balance</p>
      </div>

      {/* Overdue Accounts */}
      <div className="bg-white rounded-xl p-5 border border-slate-200 shadow-xs">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Overdue Accounts
          </span>
          <div className="w-8 h-8 rounded-lg bg-amber-50 flex items-center justify-center text-amber-600">
            <AlertTriangle className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-2 flex items-baseline justify-between">
          <p className="text-2xl font-bold text-amber-700">
            {summary.overdueCount}
          </p>
          <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md">
            Needs Reminder
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">Past payment commitment date</p>
      </div>
    </div>
  );
};
