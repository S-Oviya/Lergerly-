import React, { useState } from 'react';
import { TabType, Customer } from './types';
import { useLedger } from './hooks/useLedger';
import { Navbar } from './components/layout/Navbar';
import { TabNavigation } from './components/layout/TabNavigation';
import { DashboardPage } from './pages/DashboardPage';
import { CustomersPage } from './pages/CustomersPage';
import { TransactionsPage } from './pages/TransactionsPage';
import { AddTransactionModal } from './components/transactions/AddTransactionModal';
import { CustomerLedgerModal } from './components/customers/CustomerLedgerModal';

export function App() {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

  const {
    customers,
    transactions,
    summary,
    latestNLResult,
    addTransaction,
    processNaturalLanguage,
    clearLatestNLResult,
    resetData,
  } = useLedger();

  // Keep selectedCustomer synced if its balance updates
  const activeCustomer = selectedCustomer
    ? customers.find((c) => c.id === selectedCustomer.id) || selectedCustomer
    : null;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-['Plus_Jakarta_Sans',sans-serif]">
      {/* 1. Shopkeeper Header */}
      <Navbar
        onOpenAddModal={() => setIsAddModalOpen(true)}
        onResetData={resetData}
      />

      {/* 2. Navigation Tabs */}
      <TabNavigation
        activeTab={activeTab}
        onTabChange={setActiveTab}
        customerCount={customers.length}
        transactionCount={transactions.length}
      />

      {/* 3. Main Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        {activeTab === 'dashboard' && (
          <DashboardPage
            summary={summary}
            customers={customers}
            transactions={transactions}
            latestNLResult={latestNLResult}
            onProcessCommand={processNaturalLanguage}
            onClearResult={clearLatestNLResult}
            onSelectCustomer={(c) => setSelectedCustomer(c)}
            onViewAllTransactions={() => setActiveTab('transactions')}
          />
        )}

        {activeTab === 'customers' && (
          <CustomersPage
            customers={customers}
            onSelectCustomer={(c) => setSelectedCustomer(c)}
            onOpenAddModal={() => setIsAddModalOpen(true)}
          />
        )}

        {activeTab === 'transactions' && (
          <TransactionsPage
            transactions={transactions}
            onOpenAddModal={() => setIsAddModalOpen(true)}
          />
        )}
      </main>

      {/* 4. Footer */}
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <p>
            <strong>Ledgerly</strong> • AI-Powered Credit & Payment Assistant for Kirana Stores
          </p>
          <p className="text-slate-400">
            Phase 1 Frontend • Built for WeMakeDevs + AWS First Commit Hackathon 2026
          </p>
        </div>
      </footer>

      {/* 5. Modals */}
      <AddTransactionModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        existingCustomers={customers}
        onAddTransaction={addTransaction}
      />

      <CustomerLedgerModal
        customer={activeCustomer}
        transactions={transactions}
        onClose={() => setSelectedCustomer(null)}
        onAddTransaction={(data) => {
          addTransaction({
            customerName: data.customerName,
            type: data.type,
            amount: data.amount,
            itemsNote: data.itemsNote,
          });
        }}
      />
    </div>
  );
}

export default App;
