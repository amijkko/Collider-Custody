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
  status: DepositStatus;
  confirmations: number;
  kyt_result: KYTResult | null;
  created_at: string;
  updated_at: string;
  approved_by: string | null;
  approved_at: string | null;
}

export type DepositStatus = 'PENDING_CONFIRMATION' | 'PENDING_KYT' | 'PENDING_ADMIN' | 'APPROVED' | 'REJECTED' | 'CREDITED';
export type KYTResult = 'ALLOW' | 'REVIEW' | 'BLOCK';

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
  confirmations: number;
  required_approvals: number;
  approvals: Approval[];
  created_at: string;
  updated_at: string;
  created_by: string;
}

export type WithdrawStatus = 
  | 'SUBMITTED'
  | 'KYT_PENDING' | 'KYT_BLOCKED' | 'KYT_REVIEW'
  | 'POLICY_PENDING' | 'POLICY_BLOCKED'
  | 'APPROVAL_PENDING'
  | 'SIGN_PENDING' | 'SIGNED' | 'FAILED_SIGN'
  | 'BROADCAST_PENDING' | 'BROADCASTED' | 'FAILED_BROADCAST'
  | 'CONFIRMING' | 'FINALIZED' | 'FAILED'
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
  audit_events: AuditEvent[];
  verification: {
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

