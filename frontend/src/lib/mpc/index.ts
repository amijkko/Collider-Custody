/**
 * MPC Client Library
 * 
 * Provides client-side MPC functionality for:
 * - DKG (Distributed Key Generation) for wallet creation
 * - 2PC tECDSA signing for transactions
 * - Encrypted share storage in IndexedDB
 */

// Crypto utilities
export {
  encryptShare,
  decryptShare,
  validatePassword,
  secureWipe,
  uint8ArrayToBase64,
  base64ToUint8Array,
  uint8ArrayToHex,
  hexToUint8Array,
  type EncryptedShare,
} from './crypto';

// Storage utilities
export {
  saveShare,
  getShare,
  getShareByWalletId,
  getShareByAddress,
  listShares,
  deleteShare,
  hasShare,
  isSupported,
  clearAllShares,
  exportShare,
  importShare,
} from './storage';

// MPC Client
export {
  MPCClient,
  createMPCClient,
  type DKGResult,
  type SigningResult,
  type MPCClientConfig,
} from './client';

