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
// Note: Deposits endpoints return DepositListResponse directly (not wrapped in CorrelatedResponse)
export const depositsApi = {
  list: async (params?: { wallet_id?: string; status?: string }) => {
    const query = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    // Returns { data: Deposit[], total, correlation_id } directly
    const response = await fetch(
      `${CORE_API_URL}/v1/deposits${query}`,
      {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('access_token') || '' : ''}`,
        },
      }
    );
    return response.json() as Promise<{ data: import('@/types').Deposit[]; total: number; correlation_id: string }>;
  },

  listAdmin: async (params?: { wallet_id?: string; status?: string }) => {
    const query = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    const response = await fetch(
      `${CORE_API_URL}/v1/deposits/admin${query}`,
      {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('access_token') || '' : ''}`,
        },
      }
    );
    return response.json() as Promise<{ data: import('@/types').Deposit[]; total: number; correlation_id: string }>;
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

  getAuditPackage: async (id: string) => {
    return apiFetch<import('@/types').DepositAuditPackage>(`/v1/deposits/${id}/audit`);
  },
};

// Groups API
export const groupsApi = {
  seed: async () => {
    return apiFetch<{ message: string; created: any }>('/v1/groups/seed', {
      method: 'POST',
    });
  },

  list: async () => {
    return apiFetch<{ groups: import('@/types').Group[]; total: number }>('/v1/groups');
  },

  get: async (id: string) => {
    return apiFetch<import('@/types').Group>(`/v1/groups/${id}`);
  },

  create: async (data: { name: string; description?: string; is_default?: boolean }) => {
    return apiFetch<import('@/types').Group>('/v1/groups', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Address Book
  listAddresses: async (groupId: string, kind?: 'ALLOW' | 'DENY') => {
    const query = kind ? `?kind=${kind}` : '';
    return apiFetch<import('@/types').AddressBookList>(`/v1/groups/${groupId}/addresses${query}`);
  },

  addAddress: async (groupId: string, data: { address: string; kind: 'ALLOW' | 'DENY'; label?: string }) => {
    return apiFetch<import('@/types').AddressBookEntry>(`/v1/groups/${groupId}/addresses`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  removeAddress: async (groupId: string, address: string) => {
    return apiFetch<{ message: string }>(`/v1/groups/${groupId}/addresses/${address}`, {
      method: 'DELETE',
    });
  },

  checkAddress: async (groupId: string, address: string) => {
    return apiFetch<import('@/types').AddressCheckResult>(`/v1/groups/${groupId}/addresses/check/${address}`);
  },

  // Policies
  listPolicies: async () => {
    return apiFetch<{ policy_sets: import('@/types').PolicySet[]; total: number }>('/v1/groups/policies');
  },

  getPolicy: async (policySetId: string) => {
    return apiFetch<import('@/types').PolicySet>(`/v1/groups/policies/${policySetId}`);
  },

  createPolicy: async (data: { name: string; description?: string }) => {
    return apiFetch<import('@/types').PolicySet>('/v1/groups/policies', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updatePolicy: async (policySetId: string, data: { name?: string; description?: string; is_active?: boolean }) => {
    return apiFetch<import('@/types').PolicySet>(`/v1/groups/policies/${policySetId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deletePolicy: async (policySetId: string) => {
    return apiFetch<{ message: string }>(`/v1/groups/policies/${policySetId}`, {
      method: 'DELETE',
    });
  },

  assignPolicy: async (groupId: string, policySetId: string) => {
    return apiFetch<import('@/types').Group>(`/v1/groups/${groupId}/policy`, {
      method: 'POST',
      body: JSON.stringify({ policy_set_id: policySetId }),
    });
  },

  previewPolicy: async (groupId: string, data: { to_address: string; amount: string; asset?: string }) => {
    return apiFetch<import('@/types').PolicyEvalPreview>(`/v1/groups/${groupId}/policy/preview`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Policy Rules
  addRule: async (policySetId: string, data: {
    rule_id: string;
    priority: number;
    conditions: Record<string, any>;
    decision: 'ALLOW' | 'BLOCK' | 'CONTINUE';
    kyt_required?: boolean;
    approval_required?: boolean;
    approval_count?: number;
    description?: string;
  }) => {
    return apiFetch<import('@/types').PolicyRule>(`/v1/groups/policies/${policySetId}/rules`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateRule: async (policySetId: string, ruleId: string, data: {
    priority?: number;
    conditions?: Record<string, any>;
    decision?: 'ALLOW' | 'BLOCK' | 'CONTINUE';
    kyt_required?: boolean;
    approval_required?: boolean;
    approval_count?: number;
    description?: string;
  }) => {
    return apiFetch<import('@/types').PolicyRule>(`/v1/groups/policies/${policySetId}/rules/${ruleId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deleteRule: async (policySetId: string, ruleId: string) => {
    return apiFetch<{ message: string }>(`/v1/groups/policies/${policySetId}/rules/${ruleId}`, {
      method: 'DELETE',
    });
  },
};

