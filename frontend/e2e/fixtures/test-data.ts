/**
 * E2E Test Data Constants
 *
 * These constants are used across all E2E tests for consistency.
 * Addresses should be configured in the backend's address book.
 */

export const TEST_ADDRESSES = {
  // Allowlisted address - transactions to this address are allowed
  ALLOW_ADDR: '0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c',

  // Graylist address - triggers KYT REVIEW
  GRAY_ADDR: '0x1234567890123456789012345678901234567890',

  // Denylist address - immediately blocked (fail-fast)
  DENY_ADDR: '0xdead000000000000000000000000000000000000',

  // Funding wallet for golden path tests (EOA)
  FUNDING_WALLET: '0xB30545A8D068a3cDF3fa816245b523d0C11e3ADE',

  // Random address not in any list
  UNKNOWN_ADDR: '0x9999999999999999999999999999999999999999',
};

export const AMOUNTS = {
  // Micro payment - below threshold, skips KYT/approval (RET-01)
  MICRO: '0.0005',

  // Large payment - above threshold, requires KYT + approval (RET-02)
  LARGE: '0.01',

  // Policy threshold
  THRESHOLD: '0.001',

  // Minimum for tests
  MIN: '0.0001',

  // For golden path funding (deposit to user wallet)
  FUNDING: '0.005',
};

export const POLICY_RULES = {
  MICRO_ALLOW: 'RET-01',
  LARGE_KYT_APPROVAL: 'RET-02',
  DENYLIST_BLOCK: 'RET-03',
};

export const TX_STATUSES = {
  // Initial states
  SUBMITTED: 'SUBMITTED',
  POLICY_PENDING: 'POLICY_PENDING',

  // KYT states
  KYT_PENDING: 'KYT_PENDING',
  KYT_REVIEW: 'KYT_REVIEW',
  KYT_BLOCKED: 'KYT_BLOCKED',

  // Approval states
  APPROVAL_PENDING: 'APPROVAL_PENDING',

  // Signing states
  SIGN_PENDING: 'SIGN_PENDING',

  // Broadcast states
  BROADCAST_PENDING: 'BROADCAST_PENDING',
  MEMPOOL: 'MEMPOOL',

  // Confirmation states
  CONFIRMING: 'CONFIRMING',
  CONFIRMED: 'CONFIRMED',
  FINALIZED: 'FINALIZED',

  // Terminal failure states
  FAILED_POLICY: 'FAILED_POLICY',
  FAILED_KYT: 'FAILED_KYT',
  REJECTED: 'REJECTED',
  FAILED_SIGN: 'FAILED_SIGN',
  FAILED_BROADCAST: 'FAILED_BROADCAST',
};

export const DEPOSIT_STATUSES = {
  DETECTED: 'DETECTED',
  PENDING_CONFIRMATION: 'PENDING_CONFIRMATION',
  PENDING_KYT: 'PENDING_KYT',
  KYT_REVIEW: 'KYT_REVIEW',
  KYT_BLOCKED: 'KYT_BLOCKED',
  PENDING_ADMIN: 'PENDING_ADMIN',
  CREDITED: 'CREDITED',
  REJECTED: 'REJECTED',
};

export const KYT_RESULTS = {
  ALLOW: 'ALLOW',
  REVIEW: 'REVIEW',
  BLOCK: 'BLOCK',
  SKIPPED: 'SKIPPED',
};

export const TIMEOUTS = {
  // Standard page load
  PAGE_LOAD: 15000,

  // API response
  API: 10000,

  // Transaction processing
  TX_PROCESSING: 30000,

  // Deposit detection (chain listener interval)
  DEPOSIT_DETECTION: 60000,

  // Block confirmation
  CONFIRMATION: 120000,

  // Golden path full test
  GOLDEN_PATH: 300000,
};
