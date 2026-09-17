/**
 * Ledgerly Frontend API Client
 * Service layer to communicate with the AWS API Gateway / Lambda backend.
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

// ----------------------------------------------------------------------------
// Request & Response Types
// ----------------------------------------------------------------------------

export interface SendMessageRequest {
  message: string;
}

export interface ExtractedTransaction {
  customerName: string;
  type: 'CREDIT' | 'PAYMENT';
  amount: number;
  description: string;
}

export interface SendMessageResponse {
  success: boolean;
  message: string;
  status: string;
  extractedTransaction?: ExtractedTransaction;
}

export interface CreateCustomerRequest {
  shopId: string;
  name: string;
  phone: string;
  customerId?: string;
}

export interface BackendCustomer {
  customerId: string;
  shopId: string;
  name: string;
  phone: string;
  balance: number;
  createdAt: string;
}

export interface CreateCustomerResponse {
  success: boolean;
  customer: BackendCustomer;
}

export interface CreateTransactionRequest {
  shopId: string;
  customerId: string;
  type: 'CREDIT' | 'PAYMENT';
  amount: number;
  description?: string;
  dueDate?: string;
  transactionId?: string;
}

export interface BackendTransaction {
  transactionId: string;
  shopId: string;
  customerId: string;
  type: 'CREDIT' | 'PAYMENT';
  amount: number;
  description?: string;
  dueDate?: string;
  createdAt: string;
  updatedCustomerBalance: number;
}

export interface CreateTransactionResponse {
  success: boolean;
  transaction: BackendTransaction;
}

// ----------------------------------------------------------------------------
// HTTP Helper
// ----------------------------------------------------------------------------

export interface ApiError extends Error {
  status?: number;
  data?: unknown;
}

async function request<T>(endpoint: string, options: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg = data?.error || data?.message || response.statusText || 'API request failed';
    const err: ApiError = new Error(`API Error [${response.status}]: ${errorMsg}`);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data as T;
}

// ----------------------------------------------------------------------------
// API Service Methods
// ----------------------------------------------------------------------------

/**
 * Sends a natural language message from the shopkeeper.
 * Route: POST /message
 */
export async function sendMessage(message: string): Promise<SendMessageResponse> {
  return request<SendMessageResponse>('/message', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

/**
 * Registers a new customer under a shop.
 * Route: POST /customers
 */
export async function createCustomer(
  customer: CreateCustomerRequest
): Promise<CreateCustomerResponse> {
  return request<CreateCustomerResponse>('/customers', {
    method: 'POST',
    body: JSON.stringify(customer),
  });
}

/**
 * Appends a credit or payment transaction to a customer's ledger.
 * Route: POST /transactions
 */
export async function createTransaction(
  transaction: CreateTransactionRequest
): Promise<CreateTransactionResponse> {
  return request<CreateTransactionResponse>('/transactions', {
    method: 'POST',
    body: JSON.stringify(transaction),
  });
}
