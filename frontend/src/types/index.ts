// User types
export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export type UserRole = 'ADMIN' | 'OPERATOR' | 'COMPLIANCE' | 'VIEWER';

export interface AuthTokens {
  access_token: string;
  token_type: string;
}

// Wallet types
export interface Wallet {
  id: string;
  address: string | null;
  wallet_type: WalletType;
  subject_id: string;
  tags: Record<string, string> | null;
  risk_profile: RiskProfile;
  custody_backend: CustodyBackend;
  status: WalletStatus;
  key_ref: string;
  mpc_keyset_id: string | null;
  mpc_threshold_t: number | null;
  mpc_total_n: number | null;
  created_at: string;
  updated_at: string;
  roles: WalletRole[];
}

export type WalletType = 'RETAIL' | 'TREASURY' | 'OPS' | 'SETTLEMENT';
export type RiskProfile = 'LOW' | 'MEDIUM' | 'HIGH';
export type CustodyBackend = 'DEV_SIGNER' | 'MPC_TECDSA';
export type WalletStatus = 'PENDING_KEYGEN' | 'ACTIVE' | 'SUSPENDED' | 'ARCHIVED';

export interface WalletRole {
  id: string;
  user_id: string;
  role: WalletRoleType;
  created_at: string;
  created_by: string;
}

export type WalletRoleType = 'OWNER' | 'ADMIN' | 'OPERATOR' | 'VIEWER' | 'APPROVER';

// Balance / Ledger types
export interface LedgerBalance {
  wallet_id: string;
  asset: string;
  pending: string;
  available: string;
  locked: string;
  updated_at: string;
}

// Deposit types
export interface Deposit {
  id: string;
  wallet_id: string;
  tx_hash: string;
  from_address: string;
  amount: string;
  asset: string;
  block_number?: number;
  status: DepositStatus;
  kyt_result: KYTResult | null;
  kyt_case_id?: string | null;
  detected_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

export type DepositStatus = 'PENDING_CONFIRMATION' | 'PENDING_KYT' | 'PENDING_ADMIN' | 'APPROVED' | 'REJECTED' | 'CREDITED';
export type KYTResult = 'ALLOW' | 'REVIEW' | 'BLOCK';

export interface DepositAuditPackage {
  deposit_id: string;
  deposit: {
    id: string;
    wallet_id: string;
    wallet_address: string | null;
    tx_hash: string;
    from_address: string;
    asset: string;
    amount: string;
    block_number: number | null;
    status: string;
    kyt_result: string | null;
    kyt_case_id: string | null;
    detected_at: string | null;
    approved_by: string | null;
    approved_at: string | null;
    rejected_by: string | null;
    rejected_at: string | null;
    rejection_reason: string | null;
  };
  kyt_evaluation: Record<string, any> | null;
  admin_decision: {
    decision: 'APPROVED' | 'REJECTED';
    decided_by: string;
    decided_at: string;
    reason?: string | null;
    payload?: Record<string, any>;
  } | null;
  audit_events: AuditEvent[];
  package_hash: string;
  generated_at: string;
}

// Withdraw / Transaction types
export interface WithdrawRequest {
  id: string;
  wallet_id: string;
  to_address: string;
  amount: string;
  asset: string;
  status: WithdrawStatus;
  tx_hash: string | null;
  signed_tx: string | null;
  nonce: number | null;
  gas_limit: number | null;
  gas_price: number | null;
  block_number: number | null;
  confirmations: number;
  required_approvals: number;
  requires_approval: boolean;
  kyt_result: KYTResult | null;
  policy_result: TxPolicyResult | null;
  approvals: Approval[];
  created_at: string;
  updated_at: string;
  created_by: string;
  permit_expires_at: string | null;
}

export type WithdrawStatus =
  | 'SUBMITTED'
  | 'POLICY_EVAL_PENDING' | 'POLICY_BLOCKED'
  | 'KYT_PENDING' | 'KYT_SKIPPED' | 'KYT_BLOCKED' | 'KYT_REVIEW'
  | 'APPROVAL_PENDING' | 'APPROVAL_SKIPPED'
  | 'SIGN_PENDING' | 'SIGNED' | 'FAILED_SIGN'
  | 'BROADCAST_PENDING' | 'BROADCASTED' | 'FAILED_BROADCAST'
  | 'CONFIRMING' | 'CONFIRMED' | 'FINALIZED' | 'FAILED'
  | 'REJECTED';

export interface Approval {
  id: string;
  user_id: string;
  decision: ApprovalDecision;
  comment: string | null;
  created_at: string;
}

export type ApprovalDecision = 'APPROVED' | 'REJECTED';

// Signing Job types
export interface SigningJob {
  id: string;
  withdraw_request_id: string;
  wallet_id: string;
  keyset_id: string;
  tx_hash_to_sign: string;
  status: SigningJobStatus;
  session_id: string | null;
  requires_user_signature: boolean;
  created_at: string;
  updated_at: string;
  expires_at: string;
}

export type SigningJobStatus = 'PENDING_USER' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED' | 'EXPIRED';

// MPC types
export interface MPCKeyset {
  id: string;
  wallet_id: string;
  threshold: number;
  total: number;
  public_key_compressed: string;
  address: string;
  status: MPCKeysetStatus;
  cluster_id: string;
  key_ref: string;
  created_at: string;
  activated_at: string | null;
  last_used_at: string | null;
}

export type MPCKeysetStatus = 'PENDING' | 'DKG_IN_PROGRESS' | 'ACTIVE' | 'ROTATING' | 'COMPROMISED' | 'ARCHIVED';

export interface KeygenSession {
  session_id: string;
  status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
  step: number;
  total_steps: number;
}

export interface SigningSession {
  session_id: string;
  status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
  step: number;
  total_steps: number;
}

// Audit types
export interface AuditEvent {
  id: string;
  sequence_number: number;
  timestamp: string;
  event_type: string;
  actor_id: string | null;
  actor_type: string | null;
  entity_type: string | null;
  entity_id: string | null;
  payload: Record<string, any>;
  prev_hash: string;
  hash: string;
}

export interface AuditPackage {
  tx_request_id: string;
  tx_request: Record<string, any>;
  policy_evaluation: Record<string, any> | null;
  kyt_evaluation: Record<string, any> | null;
  approvals: Array<{
    id: string;
    user_id: string;
    decision: string;
    comment: string | null;
    created_at: string;
  }>;
  signing: Record<string, any> | null;
  broadcast: Record<string, any> | null;
  confirmations: Record<string, any> | null;
  audit_events: AuditEvent[];
  package_hash: string;
  generated_at: string;
  verification?: {
    is_valid: boolean;
    chain_length: number;
    first_event: string;
    last_event: string;
  };
}

// API Response types
export interface ApiResponse<T> {
  correlation_id: string;
  data: T;
}

export interface ApiError {
  detail: string;
  correlation_id?: string;
}

// Encrypted Share storage
export interface EncryptedShare {
  version: number;
  walletId: string;
  keysetId: string;
  cipherSuite: string;
  kdf: {
    name: string;
    hash: string;
    iterations: number;
    salt_b64: string;
  };
  enc: {
    name: string;
    iv_b64: string;
    ciphertext_b64: string;
  };
  createdAt: string;
}

// Group types
export interface Group {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
  member_count: number;
  allowlist_count: number;
  denylist_count: number;
  policy_set_id: string | null;
  policy_set_name: string | null;
  created_at: string;
}

export type AddressKind = 'ALLOW' | 'DENY';

export interface AddressBookEntry {
  id: string;
  address: string;
  kind: AddressKind;
  label: string | null;
  created_at: string;
}

export interface AddressBookList {
  entries: AddressBookEntry[];
  total: number;
  allowlist_count: number;
  denylist_count: number;
}

export interface AddressCheckResult {
  address: string;
  status: 'allowlist' | 'denylist' | 'unknown';
  label: string | null;
}

// Policy types
export type PolicyDecision = 'ALLOW' | 'BLOCK' | 'CONTINUE';

export interface PolicyRule {
  id: string;
  rule_id: string;
  priority: number;
  conditions: Record<string, any>;
  decision: PolicyDecision;
  kyt_required: boolean;
  approval_required: boolean;
  approval_count: number;
  description: string | null;
}

export interface PolicySet {
  id: string;
  name: string;
  version: number;
  description: string | null;
  is_active: boolean;
  snapshot_hash: string | null;
  rules: PolicyRule[];
  created_at: string;
}

export interface PolicyEvalPreview {
  decision: string;
  allowed: boolean;
  matched_rules: string[];
  reasons: string[];
  kyt_required: boolean;
  approval_required: boolean;
  approval_count: number;
  address_status: 'allowlist' | 'denylist' | 'unknown';
  address_label: string | null;
  policy_version: string;
}

// Transaction policy result (stored on tx)
export interface TxPolicyResult {
  decision: string;
  allowed: boolean;
  matched_rules: string[];
  reasons: string[];
  kyt_required: boolean;
  approval_required: boolean;
  approval_count: number;
  policy_version: string;
  policy_snapshot_hash: string;
  group_id: string | null;
  group_name: string | null;
  address_status: string;
  address_label: string | null;
  evaluated_at: string;
}

