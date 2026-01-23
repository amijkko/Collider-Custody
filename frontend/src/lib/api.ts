import { ApiError, ApiResponse } from '@/types';

const CORE_API_URL = process.env.NEXT_PUBLIC_CORE_API_URL || 'http://localhost:8000';

console.log('API URL:', CORE_API_URL);

interface FetchOptions extends RequestInit {
  skipAuth?: boolean;
}

function generateCorrelationId(): string {
  return `web-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export async function apiFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  const { skipAuth = false, headers: customHeaders, ...rest } = options;
  
  const correlationId = generateCorrelationId();
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Correlation-ID': correlationId,
    ...(customHeaders as Record<string, string>),
  };

  // Add auth token if available and not skipped
  if (!skipAuth && typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const url = endpoint.startsWith('http') ? endpoint : `${CORE_API_URL}${endpoint}`;
  
  console.log('API Request:', url);
  
  const response = await fetch(url, {
    ...rest,
    headers,
  });
  console.log('API Response status:', response.status);

  if (!response.ok) {
    const errorData: ApiError = await response.json().catch(() => ({
      detail: `HTTP ${response.status}: ${response.statusText}`,
      correlation_id: correlationId,
    }));
    throw new ApiRequestError(
      errorData.detail || 'An error occurred',
      response.status,
      correlationId
    );
  }

  return response.json();
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public status: number,
    public correlationId: string
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

// Auth API
export const authApi = {
  register: async (data: { username: string; email: string; password: string; role?: string }) => {
    return apiFetch<{ id: string; username: string; email: string }>('/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    });
  },

  login: async (data: { username: string; password: string }) => {
    return apiFetch<{ access_token: string; token_type: string }>('/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    });
  },

  me: async () => {
    return apiFetch<{
      id: string;
      username: string;
      email: string;
      role: string;
      is_active: boolean;
    }>('/v1/auth/me');
  },
};

// Wallets API
export const walletsApi = {
  list: async (params?: { wallet_type?: string; custody_backend?: string; status?: string }) => {
    const query = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return apiFetch<import('@/types').Wallet[]>(`/v1/wallets${query}`);
  },

  get: async (id: string) => {
    return apiFetch<import('@/types').Wallet>(`/v1/wallets/${id}`);
  },

  create: async (data: {
    wallet_type: string;
    subject_id: string;
    tags?: Record<string, string>;
    risk_profile?: string;
    custody_backend?: string;
    mpc_threshold_t?: number;
    mpc_total_n?: number;
  }) => {
    return apiFetch<import('@/types').Wallet>('/v1/wallets', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  createMPC: async (data: {
    wallet_type: string;
    subject_id: string;
    tags?: Record<string, string>;
    risk_profile?: string;
    mpc_threshold_t: number;
    mpc_total_n: number;
  }) => {
    return apiFetch<import('@/types').Wallet>('/v1/wallets/mpc', {
      method: 'POST',
      body: JSON.stringify({
        ...data,
        custody_backend: 'MPC_TECDSA',
      }),
    });
  },

  getMPCInfo: async (walletId: string) => {
    return apiFetch<import('@/types').MPCKeyset>(`/v1/wallets/${walletId}/mpc`);
  },

  assignRole: async (walletId: string, data: { user_id: string; role: string }) => {
    return apiFetch<import('@/types').WalletRole>(`/v1/wallets/${walletId}/roles`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getBalance: async (walletId: string) => {
    return apiFetch<{ wallet_id: string; address: string; balance_eth: string; balance_wei: string }>(`/v1/wallets/${walletId}/balance`);
  },

  getLedgerBalance: async (walletId: string) => {
    return apiFetch<{
      wallet_id: string;
      address: string;
      available_eth: string;
      available_wei: string;
      pending_eth: string;
      pending_wei: string;
      total_credited: number;
      total_pending: number;
    }>(`/v1/wallets/${walletId}/ledger-balance`);
  },
};

// Transaction Requests (Withdrawals) API
export const txRequestsApi = {
  list: async (params?: { wallet_id?: string; status?: string }) => {
    const query = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return apiFetch<import('@/types').WithdrawRequest[]>(`/v1/tx-requests${query}`);
  },

  get: async (id: string) => {
    return apiFetch<import('@/types').WithdrawRequest>(`/v1/tx-requests/${id}`);
  },

  create: async (data: {
    wallet_id: string;
    tx_type: string;
    to_address: string;
    asset: string;
    amount: string;
    data?: string;
  }) => {
    return apiFetch<import('@/types').WithdrawRequest>('/v1/tx-requests', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  approve: async (id: string, data: { decision: 'APPROVED' | 'REJECTED'; comment?: string }) => {
    return apiFetch<import('@/types').Approval>(`/v1/tx-requests/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  sign: async (id: string) => {
    return apiFetch<import('@/types').WithdrawRequest>(`/v1/tx-requests/${id}/sign`, {
      method: 'POST',
    });
  },
};

// Audit API
export const auditApi = {
  getPackage: async (txRequestId: string) => {
    return apiFetch<import('@/types').AuditPackage>(`/v1/audit/packages/${txRequestId}`);
  },

  verify: async (txRequestId: string) => {
    return apiFetch<{ is_valid: boolean; chain_length: number }>(`/v1/audit/verify/${txRequestId}`);
  },
};

// Cases (KYT) API
export const casesApi = {
  list: async (params?: { status?: string }) => {
    const query = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return apiFetch<any[]>(`/v1/cases${query}`);
  },

  resolve: async (id: string, data: { decision: 'ALLOW' | 'BLOCK'; comment?: string }) => {
    return apiFetch<any>(`/v1/cases/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

// Deposits API
export const depositsApi = {
  list: async (params?: { wallet_id?: string; status?: string }) => {
    const query = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return apiFetch<{ data: import('@/types').Deposit[]; total: number; correlation_id: string }>(`/v1/deposits${query}`);
  },

  listAdmin: async (params?: { wallet_id?: string; status?: string }) => {
    const query = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return apiFetch<{ data: import('@/types').Deposit[]; total: number; correlation_id: string }>(`/v1/deposits/admin${query}`);
  },

  get: async (id: string) => {
    return apiFetch<import('@/types').Deposit>(`/v1/deposits/${id}`);
  },

  approve: async (id: string) => {
    return apiFetch<import('@/types').Deposit>(`/v1/deposits/${id}/approve`, {
      method: 'POST',
    });
  },

  reject: async (id: string, reason?: string) => {
    return apiFetch<import('@/types').Deposit>(`/v1/deposits/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },
};

