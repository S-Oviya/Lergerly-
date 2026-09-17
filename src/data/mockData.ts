import { Customer, Transaction } from '../types';

export const INITIAL_CUSTOMERS: Customer[] = [
  {
    id: 'cust-1',
    name: 'Rahul Sharma',
    phone: '0000000000',
    balance: 500,
    lastTransactionDate: '2026-09-17T16:30:00Z',
    dueDate: '2026-09-19T23:59:59Z',
    notes: 'Demo customer, pays weekly',
  },
  {
    id: 'cust-2',
    name: 'Priya Patel',
    phone: '0000000000',
    balance: 1250,
    lastTransactionDate: '2026-09-14T11:15:00Z',
    dueDate: '2026-09-16T18:00:00Z', // overdue
    notes: 'Bought pulses, oil & cooking spices',
  },
  {
    id: 'cust-3',
    name: 'Amit Verma',
    phone: '0000000000',
    balance: 240,
    lastTransactionDate: '2026-09-17T10:00:00Z',
    dueDate: '2026-09-22T18:00:00Z',
    notes: 'Milk and tea leaves',
  },
  {
    id: 'cust-4',
    name: 'Sunita Devi',
    phone: '0000000000',
    balance: 1800,
    lastTransactionDate: '2026-09-10T14:45:00Z',
    dueDate: '2026-09-15T20:00:00Z', // overdue
    notes: 'Monthly grocery provision pack',
  },
  {
    id: 'cust-5',
    name: 'Suresh Kumar',
    phone: '0000000000',
    balance: 0,
    lastTransactionDate: '2026-09-17T12:20:00Z',
    notes: 'Account cleared today in cash',
  },
];

export const INITIAL_TRANSACTIONS: Transaction[] = [
  {
    id: 'tx-1',
    customerId: 'cust-1',
    customerName: 'Rahul Sharma',
    type: 'CREDIT',
    amount: 500,
    itemsNote: '2 packets of basmati rice',
    timestamp: '2026-09-17T16:30:00Z',
    dueDate: '2026-09-19T23:59:59Z',
  },
  {
    id: 'tx-2',
    customerId: 'cust-5',
    customerName: 'Suresh Kumar',
    type: 'PAYMENT',
    amount: 750,
    itemsNote: 'Cash settlement for September grains',
    timestamp: '2026-09-17T12:20:00Z',
  },
  {
    id: 'tx-3',
    customerId: 'cust-3',
    customerName: 'Amit Verma',
    type: 'CREDIT',
    amount: 240,
    itemsNote: '2L Cow Milk & Red Label Tea',
    timestamp: '2026-09-17T10:00:00Z',
    dueDate: '2026-09-22T18:00:00Z',
  },
  {
    id: 'tx-4',
    customerId: 'cust-2',
    customerName: 'Priya Patel',
    type: 'CREDIT',
    amount: 1250,
    itemsNote: 'Sunflower oil 5L tin & toor dal',
    timestamp: '2026-09-14T11:15:00Z',
    dueDate: '2026-09-16T18:00:00Z',
  },
  {
    id: 'tx-5',
    customerId: 'cust-4',
    customerName: 'Sunita Devi',
    type: 'CREDIT',
    amount: 1800,
    itemsNote: 'Atta 10kg, Sugar 5kg, Spices',
    timestamp: '2026-09-10T14:45:00Z',
    dueDate: '2026-09-15T20:00:00Z',
  },
  {
    id: 'tx-6',
    customerId: 'cust-4',
    customerName: 'Sunita Devi',
    type: 'PAYMENT',
    amount: 500,
    itemsNote: 'Partial UPI payment',
    timestamp: '2026-09-12T17:00:00Z',
  },
];

export const SAMPLE_QUICK_COMMANDS = [
  'Rahul took 2 packets of rice for 500, he\'ll pay Friday',
  'Rahul paid 300',
  'Priya paid 500 via cash',
  'Amit took 1kg sugar and soap for 160 on credit',
  'Suresh took mustard oil for 220, promise Sunday',
];
