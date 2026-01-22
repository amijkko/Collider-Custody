/**
 * Client-side cryptography utilities for MPC share management.
 * Uses WebCrypto API for secure key derivation and encryption.
 */

// Constants
const PBKDF2_ITERATIONS = 310000;
const SALT_SIZE = 32;
const IV_SIZE = 12;
const KEY_SIZE = 256; // bits

/**
 * Encrypted share format stored in IndexedDB
 */
export interface EncryptedShare {
  version: 1;
  walletId: string;
  keysetId: string;
  cipherSuite: 'secp256k1-tecdsa-2pc';
  kdf: {
    name: 'PBKDF2';
    hash: 'SHA-256';
    iterations: number;
    salt_b64: string;
  };
  enc: {
    name: 'AES-GCM';
    iv_b64: string;
    ciphertext_b64: string;
  };
  publicKey: string;
  ethereumAddress: string;
  createdAt: string;
}

/**
 * Derives an encryption key from password using PBKDF2
 */
export async function deriveKey(
  password: string,
  salt: Uint8Array
): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  const passwordBuffer = encoder.encode(password);

  // Import password as key material
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    passwordBuffer,
    'PBKDF2',
    false,
    ['deriveBits', 'deriveKey']
  );

  // Derive AES-GCM key
  // Create a new ArrayBuffer from salt to ensure compatibility with WebCrypto API
  const saltArray = new Uint8Array(salt);
  const saltBuffer = new ArrayBuffer(saltArray.length);
  new Uint8Array(saltBuffer).set(saltArray);
  
  // Type assertion to work around TypeScript strictness with ArrayBufferLike
  const pbkdf2Params: Pbkdf2Params = {
    name: 'PBKDF2',
    salt: saltBuffer,
    iterations: PBKDF2_ITERATIONS,
    hash: 'SHA-256',
  };
  
  return crypto.subtle.deriveKey(
    pbkdf2Params as any,
    keyMaterial,
    { name: 'AES-GCM', length: KEY_SIZE },
    false,
    ['encrypt', 'decrypt']
  );
}

/**
 * Encrypts data using AES-GCM
 */
export async function encrypt(
  data: Uint8Array,
  key: CryptoKey
): Promise<{ ciphertext: Uint8Array; iv: Uint8Array }> {
  const iv = crypto.getRandomValues(new Uint8Array(IV_SIZE));

  // Ensure data is a proper ArrayBuffer for WebCrypto API
  const dataArray = new Uint8Array(data);
  const dataBuffer = new ArrayBuffer(dataArray.length);
  new Uint8Array(dataBuffer).set(dataArray);
  
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: iv },
    key,
    dataBuffer as any // TypeScript strictness issue
  );

  return {
    ciphertext: new Uint8Array(ciphertext),
    iv: iv,
  };
}

/**
 * Decrypts data using AES-GCM
 */
export async function decrypt(
  ciphertext: Uint8Array,
  iv: Uint8Array,
  key: CryptoKey
): Promise<Uint8Array> {
  // Ensure iv and ciphertext are proper ArrayBuffers for WebCrypto API
  const ivArray = new Uint8Array(iv);
  const ivBuffer = new ArrayBuffer(ivArray.length);
  new Uint8Array(ivBuffer).set(ivArray);
  
  const ciphertextArray = new Uint8Array(ciphertext);
  const ciphertextBuffer = new ArrayBuffer(ciphertextArray.length);
  new Uint8Array(ciphertextBuffer).set(ciphertextArray);
  
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: ivBuffer as any },
    key,
    ciphertextBuffer as any
  );

  return new Uint8Array(plaintext);
}

/**
 * Encrypts a share with a password
 */
export async function encryptShare(
  shareData: Uint8Array,
  password: string,
  walletId: string,
  keysetId: string,
  publicKey: string,
  ethereumAddress: string
): Promise<EncryptedShare> {
  // Generate random salt
  const salt = crypto.getRandomValues(new Uint8Array(SALT_SIZE));

  // Derive key from password
  const key = await deriveKey(password, salt);

  // Encrypt share data
  const { ciphertext, iv } = await encrypt(shareData, key);

  return {
    version: 1,
    walletId,
    keysetId,
    cipherSuite: 'secp256k1-tecdsa-2pc',
    kdf: {
      name: 'PBKDF2',
      hash: 'SHA-256',
      iterations: PBKDF2_ITERATIONS,
      salt_b64: uint8ArrayToBase64(salt),
    },
    enc: {
      name: 'AES-GCM',
      iv_b64: uint8ArrayToBase64(iv),
      ciphertext_b64: uint8ArrayToBase64(ciphertext),
    },
    publicKey,
    ethereumAddress,
    createdAt: new Date().toISOString(),
  };
}

/**
 * Decrypts a share with a password
 */
export async function decryptShare(
  encryptedShare: EncryptedShare,
  password: string
): Promise<Uint8Array> {
  const salt = base64ToUint8Array(encryptedShare.kdf.salt_b64);
  const iv = base64ToUint8Array(encryptedShare.enc.iv_b64);
  const ciphertext = base64ToUint8Array(encryptedShare.enc.ciphertext_b64);

  // Derive key from password
  const key = await deriveKey(password, salt);

  // Decrypt share data
  try {
    return await decrypt(ciphertext, iv, key);
  } catch (error) {
    throw new Error('Invalid password or corrupted share');
  }
}

/**
 * Validates password strength
 */
export function validatePassword(password: string): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  if (password.length < 8) {
    errors.push('Password must be at least 8 characters');
  }
  if (!/[A-Z]/.test(password)) {
    errors.push('Password must contain at least one uppercase letter');
  }
  if (!/[a-z]/.test(password)) {
    errors.push('Password must contain at least one lowercase letter');
  }
  if (!/[0-9]/.test(password)) {
    errors.push('Password must contain at least one number');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Securely clears sensitive data from memory
 */
export function secureWipe(data: Uint8Array): void {
  crypto.getRandomValues(data);
  data.fill(0);
}

// Utility functions

export function uint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function uint8ArrayToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export function hexToUint8Array(hex: string): Uint8Array {
  const cleanHex = hex.startsWith('0x') ? hex.slice(2) : hex;
  const bytes = new Uint8Array(cleanHex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(cleanHex.substr(i * 2, 2), 16);
  }
  return bytes;
}

