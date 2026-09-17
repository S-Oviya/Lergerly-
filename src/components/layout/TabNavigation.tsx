import React from 'react';
import { TabType } from '../../types';
import { LayoutDashboard, Users, ArrowLeftRight } from 'lucide-react';

interface TabNavigationProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  customerCount: number;
  transactionCount: number;
}

export const TabNavigation: React.FC<TabNavigationProps> = ({
  activeTab,
  onTabChange,
  customerCount,
  transactionCount,
}) => {
  const tabs = [
    {
      id: 'dashboard' as TabType,
      label: 'Dashboard',
      icon: LayoutDashboard,
      badge: null,
    },
    {
      id: 'customers' as TabType,
      label: 'Customers (Khata)',
      icon: Users,
      badge: customerCount,
    },
    {
      id: 'transactions' as TabType,
      label: 'Transactions',
      icon: ArrowLeftRight,
      badge: transactionCount,
    },
  ];

  return (
    <div className="border-b border-slate-200 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex space-x-6 sm:space-x-8" aria-label="Tabs">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`py-3.5 px-1 inline-flex items-center gap-2 border-b-2 font-medium text-sm transition-colors ${
                  isActive
                    ? 'border-emerald-600 text-emerald-700 font-semibold'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-600' : 'text-slate-400'}`} />
                <span>{tab.label}</span>
                {tab.badge !== null && (
                  <span
                    className={`ml-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                      isActive ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
};
