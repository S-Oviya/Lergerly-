import React from 'react';
import { Customer } from '../types';
import { CustomerList } from '../components/customers/CustomerList';

interface CustomersPageProps {
  customers: Customer[];
  onSelectCustomer: (customer: Customer) => void;
  onOpenAddModal: () => void;
}

export const CustomersPage: React.FC<CustomersPageProps> = ({
  customers,
  onSelectCustomer,
  onOpenAddModal,
}) => {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-slate-900 tracking-tight">Customer Accounts (Khata)</h2>
        <p className="text-xs text-slate-500">
          Manage individual customer credit balances, contact info, and payment records.
        </p>
      </div>

      <CustomerList
        customers={customers}
        onSelectCustomer={onSelectCustomer}
        onOpenAddModal={onOpenAddModal}
      />
    </div>
  );
};
