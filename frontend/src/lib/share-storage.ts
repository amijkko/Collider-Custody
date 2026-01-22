/**
 * IndexedDB storage for encrypted MPC shares.
 * Shares are stored encrypted and never leave the device in plaintext.
 */

import { openDB, IDBPDatabase } from 'idb';
import { EncryptedShare } from '@/types';

const DB_NAME = 'collider-custody-shares';
const DB_VERSION = 1;
const STORE_NAME = 'encrypted-shares';

interface ShareDB {
  'encrypted-shares': {
    key: string; // walletId
    value: EncryptedShare;
    indexes: { 'by-keyset': string };
  };
}

let dbPromise: Promise<IDBPDatabase<ShareDB>> | null = null;

/**
 * Get or create the database connection
 */
async function getDB(): Promise<IDBPDatabase<ShareDB>> {
  if (!dbPromise) {
    dbPromise = openDB<ShareDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'walletId' });
        store.createIndex('by-keyset', 'keysetId', { unique: true });
      },
    });
  }
  return dbPromise;
}

/**
 * Store encrypted share in IndexedDB
 */
export async function storeEncryptedShare(share: EncryptedShare): Promise<void> {
  const db = await getDB();
  await db.put(STORE_NAME, share);
}

/**
 * Get encrypted share by wallet ID
 */
export async function getEncryptedShare(walletId: string): Promise<EncryptedShare | undefined> {
  const db = await getDB();
  return db.get(STORE_NAME, walletId);
}

/**
 * Get encrypted share by keyset ID
 */
export async function getEncryptedShareByKeyset(keysetId: string): Promise<EncryptedShare | undefined> {
  const db = await getDB();
  return db.getFromIndex(STORE_NAME, 'by-keyset', keysetId);
}

/**
 * List all stored shares (metadata only for display)
 */
export async function listStoredShares(): Promise<Array<{
  walletId: string;
  keysetId: string;
  createdAt: string;
}>> {
  const db = await getDB();
  const shares = await db.getAll(STORE_NAME);
  return shares.map((s) => ({
    walletId: s.walletId,
    keysetId: s.keysetId,
    createdAt: s.createdAt,
  }));
}

/**
 * Delete encrypted share
 */
export async function deleteEncryptedShare(walletId: string): Promise<void> {
  const db = await getDB();
  await db.delete(STORE_NAME, walletId);
}

/**
 * Check if share exists for wallet
 */
export async function hasShare(walletId: string): Promise<boolean> {
  const share = await getEncryptedShare(walletId);
  return share !== undefined;
}

/**
 * Export share for backup (still encrypted)
 */
export async function exportShare(walletId: string): Promise<string | null> {
  const share = await getEncryptedShare(walletId);
  if (!share) return null;
  return JSON.stringify(share);
}

/**
 * Import share from backup
 */
export async function importShare(shareJson: string): Promise<EncryptedShare> {
  const share: EncryptedShare = JSON.parse(shareJson);
  
  // Validate structure
  if (!share.version || !share.walletId || !share.keysetId || !share.kdf || !share.enc) {
    throw new Error('Invalid share format');
  }
  
  await storeEncryptedShare(share);
  return share;
}

/**
 * Clear all stored shares (for logout/reset)
 */
export async function clearAllShares(): Promise<void> {
  const db = await getDB();
  await db.clear(STORE_NAME);
}

