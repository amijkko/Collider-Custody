/**
 * API Helpers for E2E Tests
 *
 * Direct API calls for setup, verification, and actions that
 * are faster/more reliable than UI interactions.
 */

const API_URL = process.env.E2E_API_URL || 'http://localhost:8000';

export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  correlation_id?: string;
}

/**
 * Make an API request
 */
export async function api<T = any>(
  method: string,
  endpoint: string,
  token?: string,
  body?: object
): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(`${API_URL}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    return await res.json();
  } catch (error) {
    return { error: String(error) };
  }
}

/**
 * Login and get token
 */
export async function loginApi(username: string, password: string): Promise<string | null> {
  const res = await api('POST', '/v1/auth/login', undefined, { username, password });
  return res.data?.access_token || null;
}

/**
 * Register a new user
 */
export async function registerApi(username: string, email: string, password: string): Promise<ApiResponse> {
  return api('POST', '/v1/auth/register', undefined, { username, email, password });
}

/**
 * Get user's wallets
 */
export async function getWallets(token: string): Promise<any[]> {
  const res = await api('GET', '/v1/wallets', token);
  return res.data || [];
}

/**
 * Get wallet balance
 */
export async function getWalletBalance(token: string, walletId: string): Promise<{ available_eth: string; pending_eth: string }> {
  const res = await api('GET', `/v1/wallets/${walletId}/ledger-balance`, token);
  return res.data || { available_eth: '0', pending_eth: '0' };
}

/**
 * Create a withdrawal/transfer request
 */
export async function createWithdrawal(
  token: string,
  walletId: string,
  toAddress: string,
  amountWei: string
): Promise<ApiResponse> {
  return api('POST', '/v1/tx-requests', token, {
    wallet_id: walletId,
    tx_type: 'TRANSFER',
    to_address: toAddress,
    amount: amountWei,
    asset: 'ETH',
  });
}

/**
 * Get transaction request status
 */
export async function getWithdrawal(token: string, txId: string): Promise<any> {
  const res = await api('GET', `/v1/tx-requests/${txId}`, token);
  return res.data;
}

/**
 * Approve a transaction request (admin)
 */
export async function approveWithdrawal(token: string, txId: string, comment?: string): Promise<ApiResponse> {
  return api('POST', `/v1/tx-requests/${txId}/approve`, token, {
    decision: 'APPROVED',
    comment: comment || 'E2E test approval',
  });
}

/**
 * Reject a transaction request (admin)
 */
export async function rejectWithdrawal(token: string, txId: string, reason: string): Promise<ApiResponse> {
  return api('POST', `/v1/tx-requests/${txId}/approve`, token, {
    decision: 'REJECTED',
    comment: reason,
  });
}

/**
 * Get deposits for a wallet
 */
export async function getDeposits(token: string, walletId?: string): Promise<any[]> {
  const url = walletId ? `/v1/deposits?wallet_id=${walletId}` : '/v1/deposits';
  const res = await api('GET', url, token);
  return res.data || [];
}

/**
 * Get all deposits (admin)
 */
export async function getDepositsAdmin(token: string): Promise<any[]> {
  const res = await api('GET', '/v1/deposits/admin', token);
  return res.data || [];
}

/**
 * Approve a deposit (admin)
 */
export async function approveDeposit(token: string, depositId: string): Promise<ApiResponse> {
  return api('POST', `/v1/deposits/${depositId}/approve`, token);
}

/**
 * Reject a deposit (admin)
 */
export async function rejectDeposit(token: string, depositId: string, reason?: string): Promise<ApiResponse> {
  return api('POST', `/v1/deposits/${depositId}/reject`, token, { reason });
}

/**
 * Get KYT cases
 */
export async function getCases(token: string): Promise<any[]> {
  const res = await api('GET', '/v1/cases', token);
  return res.data || [];
}

/**
 * Resolve a KYT case
 */
export async function resolveCase(
  token: string,
  caseId: string,
  decision: 'ALLOW' | 'BLOCK',
  reason: string
): Promise<ApiResponse> {
  return api('POST', `/v1/cases/${caseId}/resolve`, token, { decision, reason });
}

/**
 * Get groups
 */
export async function getGroups(token: string): Promise<any[]> {
  const res = await api('GET', '/v1/groups', token);
  // API returns { data: { groups: [...], total: N } }
  return res.data?.groups || res.data || [];
}

/**
 * Get group details
 */
export async function getGroup(token: string, groupId: string): Promise<any> {
  const res = await api('GET', `/v1/groups/${groupId}`, token);
  return res.data;
}

/**
 * Add member to group
 */
export async function addGroupMember(token: string, groupId: string, userId: string): Promise<ApiResponse> {
  return api('POST', `/v1/groups/${groupId}/members`, token, { user_id: userId });
}

/**
 * Remove member from group
 */
export async function removeGroupMember(token: string, groupId: string, userId: string): Promise<ApiResponse> {
  return api('DELETE', `/v1/groups/${groupId}/members/${userId}`, token);
}

/**
 * Get audit package for withdrawal
 */
export async function getWithdrawalAudit(token: string, txId: string): Promise<any> {
  const res = await api('GET', `/v1/withdrawals/${txId}/audit`, token);
  return res.data;
}

/**
 * Get audit package for deposit
 */
export async function getDepositAudit(token: string, depositId: string): Promise<any> {
  const res = await api('GET', `/v1/deposits/${depositId}/audit`, token);
  return res.data;
}

/**
 * Convert ETH to Wei string
 */
export function ethToWei(eth: string | number): string {
  const ethNum = typeof eth === 'string' ? parseFloat(eth) : eth;
  return Math.floor(ethNum * 1e18).toString();
}

/**
 * Convert Wei to ETH
 */
export function weiToEth(wei: string | number): number {
  const weiNum = typeof wei === 'string' ? parseFloat(wei) : wei;
  return weiNum / 1e18;
}

/**
 * Wait for transaction to reach a specific status
 */
export async function waitForTxStatus(
  token: string,
  txId: string,
  targetStatuses: string[],
  timeoutMs: number = 60000,
  pollIntervalMs: number = 2000
): Promise<any> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    const tx = await getWithdrawal(token, txId);

    if (targetStatuses.includes(tx?.status)) {
      return tx;
    }

    // Check for terminal failure states
    if (tx?.status?.startsWith('FAILED_') || tx?.status === 'REJECTED') {
      return tx;
    }

    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
  }

  throw new Error(`Timeout waiting for tx ${txId} to reach ${targetStatuses.join('/')}`);
}

/**
 * Wait for deposit to be detected
 */
export async function waitForDeposit(
  token: string,
  walletId: string,
  timeoutMs: number = 60000,
  pollIntervalMs: number = 5000
): Promise<any> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    const deposits = await getDeposits(token, walletId);
    const pending = deposits.find(d =>
      d.status === 'PENDING_ADMIN' || d.status === 'PENDING_KYT'
    );

    if (pending) {
      return pending;
    }

    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
  }

  throw new Error(`Timeout waiting for deposit on wallet ${walletId}`);
}
