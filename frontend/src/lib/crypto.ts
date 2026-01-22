/**
 * Client-side cryptography utilities for MPC share encryption.
 * Uses WebCrypto API for secure key derivation and encryption.
 * 
 * Security:
 * - Password never leaves the browser
 * - Share is encrypted at rest with AES-256-GCM
 * - Key derived with PBKDF2-SHA256 (300k+ iterations)
 */

import { EncryptedShare } from '@/types';

const PBKDF2_ITERATIONS = 310000; // OWASP recommended minimum for SHA-256
const SALT_LENGTH = 32; // 256 bits
const IV_LENGTH = 12; // 96 bits for GCM

/**
 * Generate cryptographically secure random bytes
 */
function getRandomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytes;
}

/**
 * Convert ArrayBuffer or Uint8Array to base64 string
 */
function bufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Convert base64 string to ArrayBuffer
 */
function base64ToBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Derive encryption key from password using PBKDF2
 */
async function deriveKey(
  password: string,
  salt: Uint8Array
): Promise<CryptoKey> {
  // Import password as raw key material
  const passwordKey = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    { name: 'PBKDF2' },
    false,
    ['deriveBits', 'deriveKey']
  );

  // Derive AES-GCM key
  // Create a new ArrayBuffer from salt to ensure compatibility with WebCrypto API
  const saltArray = new Uint8Array(salt);
  const saltBuffer = new ArrayBuffer(saltArray.length);
  new Uint8Array(saltBuffer).set(saltArray);
  
  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: saltBuffer as any, // TypeScript strictness issue with ArrayBufferLike, but works in runtime
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    passwordKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );
}

/**
 * Encrypt the MPC share with user's password
 */
export async function encryptShare(
  share: Uint8Array,
  password: string,
  walletId: string,
  keysetId: string
): Promise<EncryptedShare> {
  const salt = getRandomBytes(SALT_LENGTH);
  const iv = getRandomBytes(IV_LENGTH);

  const key = await deriveKey(password, salt);

  // Ensure iv is a proper ArrayBuffer for WebCrypto API
  const ivArray = new Uint8Array(iv);
  const ivBuffer = new ArrayBuffer(ivArray.length);
  new Uint8Array(ivBuffer).set(ivArray);
  
  // Ensure share is a proper ArrayBuffer for WebCrypto API
  const shareArray = new Uint8Array(share);
  const shareBuffer = new ArrayBuffer(shareArray.length);
  new Uint8Array(shareBuffer).set(shareArray);
  
  const ciphertext = await crypto.subtle.encrypt(
    {
      name: 'AES-GCM',
      iv: ivBuffer as any, // TypeScript strictness issue
    },
    key,
    shareBuffer as any // TypeScript strictness issue
  );

  return {
    version: 1,
    walletId,
    keysetId,
    cipherSuite: 'secp256k1-tecdsa-2pc',
    kdf: {
      name: 'PBKDF2',
      hash: 'SHA-256',
      iterations: PBKDF2_ITERATIONS,
      salt_b64: bufferToBase64(salt),
    },
    enc: {
      name: 'AES-GCM',
      iv_b64: bufferToBase64(iv),
      ciphertext_b64: bufferToBase64(ciphertext),
    },
    createdAt: new Date().toISOString(),
  };
}

/**
 * Decrypt the MPC share with user's password
 */
export async function decryptShare(
  encryptedShare: EncryptedShare,
  password: string
): Promise<Uint8Array> {
  const salt = new Uint8Array(base64ToBuffer(encryptedShare.kdf.salt_b64));
  const iv = new Uint8Array(base64ToBuffer(encryptedShare.enc.iv_b64));
  const ciphertext = base64ToBuffer(encryptedShare.enc.ciphertext_b64);

  const key = await deriveKey(password, salt);

  try {
    // Ensure iv is a proper ArrayBuffer for WebCrypto API
    const ivArray = new Uint8Array(iv);
    const ivBuffer = new ArrayBuffer(ivArray.length);
    new Uint8Array(ivBuffer).set(ivArray);
    
    const plaintext = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: ivBuffer as any, // TypeScript strictness issue
      },
      key,
      ciphertext
    );

    return new Uint8Array(plaintext);
  } catch (error) {
    throw new Error('Invalid password or corrupted data');
  }
}

/**
 * Securely clear sensitive data from memory
 * Note: JavaScript doesn't guarantee memory clearing, but this helps
 */
export function secureWipe(data: Uint8Array): void {
  crypto.getRandomValues(data);
  data.fill(0);
}

/**
 * Generate a random wallet derivation path or nonce
 */
export function generateRandomHex(bytes: number = 32): string {
  const randomBytes = getRandomBytes(bytes);
  return Array.from(randomBytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Hash data using SHA-256
 */
export async function sha256(data: string | Uint8Array): Promise<string> {
  const buffer = typeof data === 'string' ? new TextEncoder().encode(data) : data;
  // Ensure buffer is a proper ArrayBuffer for WebCrypto API
  const bufferArray = new Uint8Array(buffer);
  const bufferBuffer = new ArrayBuffer(bufferArray.length);
  new Uint8Array(bufferBuffer).set(bufferArray);
  const hashBuffer = await crypto.subtle.digest('SHA-256', bufferBuffer as any);
  return bufferToBase64(hashBuffer);
}

/**
 * Validate password strength
 */
export function validatePassword(password: string): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  if (password.length < 12) {
    errors.push('Password must be at least 12 characters');
  }
  if (!/[A-Z]/.test(password)) {
    errors.push('Password must contain an uppercase letter');
  }
  if (!/[a-z]/.test(password)) {
    errors.push('Password must contain a lowercase letter');
  }
  if (!/[0-9]/.test(password)) {
    errors.push('Password must contain a number');
  }
  if (!/[^A-Za-z0-9]/.test(password)) {
    errors.push('Password must contain a special character');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

