/**
 * IndexedDB storage for encrypted MPC shares.
 * Shares are stored locally and never leave the browser unencrypted.
 */

import { EncryptedShare } from './crypto';

const DB_NAME = 'collider-mpc';
const DB_VERSION = 1;
const STORE_NAME = 'shares';

let dbPromise: Promise<IDBDatabase> | null = null;

/**
 * Opens or creates the IndexedDB database
 */
function openDB(): Promise<IDBDatabase> {
  if (dbPromise) {
    return dbPromise;
  }

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => {
      reject(new Error('Failed to open IndexedDB'));
    };

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      // Create object store for shares
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'keysetId' });
        store.createIndex('walletId', 'walletId', { unique: false });
        store.createIndex('ethereumAddress', 'ethereumAddress', { unique: false });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
    };
  });

  return dbPromise;
}

/**
 * Saves an encrypted share to IndexedDB
 */
export async function saveShare(share: EncryptedShare): Promise<void> {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite');
    const store = transaction.objectStore(STORE_NAME);

    const request = store.put(share);

    request.onsuccess = () => resolve();
    request.onerror = () => reject(new Error('Failed to save share'));
  });
}

/**
 * Gets an encrypted share by keyset ID
 */
export async function getShare(keysetId: string): Promise<EncryptedShare | null> {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readonly');
    const store = transaction.objectStore(STORE_NAME);

    const request = store.get(keysetId);

    request.onsuccess = () => {
      resolve(request.result || null);
    };
    request.onerror = () => reject(new Error('Failed to get share'));
  });
}

/**
 * Gets an encrypted share by wallet ID
 */
export async function getShareByWalletId(walletId: string): Promise<EncryptedShare | null> {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readonly');
    const store = transaction.objectStore(STORE_NAME);
    const index = store.index('walletId');

    const request = index.get(walletId);

    request.onsuccess = () => {
      resolve(request.result || null);
    };
    request.onerror = () => reject(new Error('Failed to get share by wallet ID'));
  });
}

/**
 * Gets an encrypted share by Ethereum address
 */
export async function getShareByAddress(address: string): Promise<EncryptedShare | null> {
  const db = await openDB();
  const normalizedAddress = address.toLowerCase();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readonly');
    const store = transaction.objectStore(STORE_NAME);
    const index = store.index('ethereumAddress');

    const request = index.openCursor();
    
    request.onsuccess = () => {
      const cursor = request.result;
      if (cursor) {
        const share = cursor.value as EncryptedShare;
        if (share.ethereumAddress.toLowerCase() === normalizedAddress) {
          resolve(share);
          return;
        }
        cursor.continue();
      } else {
        resolve(null);
      }
    };
    request.onerror = () => reject(new Error('Failed to get share by address'));
  });
}

/**
 * Lists all encrypted shares (metadata only)
 */
export async function listShares(): Promise<EncryptedShare[]> {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readonly');
    const store = transaction.objectStore(STORE_NAME);

    const request = store.getAll();

    request.onsuccess = () => {
      resolve(request.result || []);
    };
    request.onerror = () => reject(new Error('Failed to list shares'));
  });
}

/**
 * Deletes an encrypted share
 */
export async function deleteShare(keysetId: string): Promise<void> {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite');
    const store = transaction.objectStore(STORE_NAME);

    const request = store.delete(keysetId);

    request.onsuccess = () => resolve();
    request.onerror = () => reject(new Error('Failed to delete share'));
  });
}

/**
 * Checks if a share exists for a given keyset
 */
export async function hasShare(keysetId: string): Promise<boolean> {
  const share = await getShare(keysetId);
  return share !== null;
}

/**
 * Checks if browser supports IndexedDB
 */
export function isSupported(): boolean {
  return typeof indexedDB !== 'undefined';
}

/**
 * Clears all shares (for testing/reset)
 */
export async function clearAllShares(): Promise<void> {
  const db = await openDB();

  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite');
    const store = transaction.objectStore(STORE_NAME);

    const request = store.clear();

    request.onsuccess = () => resolve();
    request.onerror = () => reject(new Error('Failed to clear shares'));
  });
}

/**
 * Export share for backup (encrypted)
 */
export async function exportShare(keysetId: string): Promise<string | null> {
  const share = await getShare(keysetId);
  if (!share) return null;

  return JSON.stringify(share);
}

/**
 * Import share from backup (encrypted)
 */
export async function importShare(shareJson: string): Promise<void> {
  try {
    const share = JSON.parse(shareJson) as EncryptedShare;
    
    // Validate share format
    if (share.version !== 1) {
      throw new Error('Unsupported share version');
    }
    if (!share.keysetId || !share.walletId || !share.enc?.ciphertext_b64) {
      throw new Error('Invalid share format');
    }

    await saveShare(share);
  } catch (error) {
    throw new Error(`Failed to import share: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

