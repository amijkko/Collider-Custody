/**
 * TypeScript wrapper for TSS WASM module.
 *
 * This module provides a type-safe interface to the Go TSS library
 * compiled to WebAssembly for browser-based MPC operations.
 */

import { keccak_256 } from 'js-sha3';

export interface DKGResult {
  keyset_id: string;
  public_key: string;
  public_key_full: string;
  ethereum_address: string;
  save_data: string; // Hex-encoded serialized save data
}

export interface SigningResult {
  signature_r: string;
  signature_s: string;
  signature_v: number;
  full_signature: string;
}

export interface IncomingMessage {
  from_party: number;
  payload: string; // Hex-encoded
}

interface WASMResult {
  success: boolean;
  error?: string;
  round1_msg?: string;
  outgoing_msg?: string;
  is_final?: boolean;
  result?: string;
  public_key?: string;
  ethereum_address?: string;
}

// Global state
let wasmInitialized = false;
let wasmInitPromise: Promise<void> | null = null;

// Declare global WASM functions (set by Go WASM)
declare global {
  function tssStartDKG(sessionId: string, partyIndex: number, threshold: number, totalParties: number): WASMResult;
  function tssDKGRound(sessionId: string, round: number, incomingMessages: IncomingMessage[]): WASMResult;
  function tssStartSigning(sessionId: string, partyIndex: number, messageHash: string, saveData: string, totalParties: number, threshold: number): WASMResult;
  function tssSigningRound(sessionId: string, round: number, incomingMessages: IncomingMessage[]): WASMResult;
  function tssLoadSaveData(saveData: string): WASMResult;
  function tssCleanupSession(sessionId: string): WASMResult;
  function keccak256(data: string): string;

  // Go WASM runtime
  class Go {
    importObject: WebAssembly.Imports;
    run(instance: WebAssembly.Instance): Promise<void>;
  }
}

/**
 * Initialize the TSS WASM module.
 * Must be called before any TSS operations.
 */
export async function initTSSWasm(): Promise<void> {
  if (wasmInitialized) {
    return;
  }

  if (wasmInitPromise) {
    return wasmInitPromise;
  }

  wasmInitPromise = (async () => {
    try {
      // Load wasm_exec.js if not already loaded
      if (typeof Go === 'undefined') {
        await loadScript('/wasm/wasm_exec.js');
      }

      // Set up keccak256 helper for Go WASM
      if (typeof window !== 'undefined') {
        (window as any).keccak256 = keccak256Hex;
      }

      // Initialize Go runtime
      const go = new Go();

      // Load WASM module
      const response = await fetch('/wasm/tss.wasm');
      const wasmBytes = await response.arrayBuffer();

      const result = await WebAssembly.instantiate(wasmBytes, go.importObject);

      // Run Go WASM (non-blocking, returns immediately)
      go.run(result.instance);

      // Wait for global functions to be registered
      await waitForGlobalFunction('tssStartDKG', 5000);

      wasmInitialized = true;
      console.log('[TSS-WASM] Initialized successfully');
    } catch (error) {
      console.error('[TSS-WASM] Initialization failed:', error);
      wasmInitPromise = null;
      throw error;
    }
  })();

  return wasmInitPromise;
}

/**
 * Check if WASM is initialized
 */
export function isWasmInitialized(): boolean {
  return wasmInitialized;
}

/**
 * Start a new DKG session
 */
export async function startDKG(
  sessionId: string,
  partyIndex: number,
  threshold: number,
  totalParties: number
): Promise<{ round1Msg: string }> {
  await initTSSWasm();

  const result = tssStartDKG(sessionId, partyIndex, threshold, totalParties);

  if (!result.success) {
    throw new Error(result.error || 'DKG start failed');
  }

  return {
    round1Msg: result.round1_msg || '',
  };
}

/**
 * Process a DKG round
 */
export async function processDKGRound(
  sessionId: string,
  round: number,
  incomingMessages: IncomingMessage[]
): Promise<{
  outgoingMsg: string;
  isFinal: boolean;
  result?: DKGResult;
}> {
  await initTSSWasm();

  const result = tssDKGRound(sessionId, round, incomingMessages);

  if (!result.success) {
    throw new Error(result.error || 'DKG round failed');
  }

  let dkgResult: DKGResult | undefined;
  if (result.is_final && result.result) {
    dkgResult = JSON.parse(result.result) as DKGResult;
  }

  return {
    outgoingMsg: result.outgoing_msg || '',
    isFinal: result.is_final || false,
    result: dkgResult,
  };
}

/**
 * Start a new signing session
 */
export async function startSigning(
  sessionId: string,
  partyIndex: number,
  messageHash: string,
  saveData: string,
  totalParties: number,
  threshold: number
): Promise<{ round1Msg: string }> {
  await initTSSWasm();

  const result = tssStartSigning(
    sessionId,
    partyIndex,
    messageHash,
    saveData,
    totalParties,
    threshold
  );

  if (!result.success) {
    throw new Error(result.error || 'Signing start failed');
  }

  return {
    round1Msg: result.round1_msg || '',
  };
}

/**
 * Process a signing round
 */
export async function processSigningRound(
  sessionId: string,
  round: number,
  incomingMessages: IncomingMessage[]
): Promise<{
  outgoingMsg: string;
  isFinal: boolean;
  result?: SigningResult;
}> {
  await initTSSWasm();

  const result = tssSigningRound(sessionId, round, incomingMessages);

  if (!result.success) {
    throw new Error(result.error || 'Signing round failed');
  }

  let signingResult: SigningResult | undefined;
  if (result.is_final && result.result) {
    signingResult = JSON.parse(result.result) as SigningResult;
  }

  return {
    outgoingMsg: result.outgoing_msg || '',
    isFinal: result.is_final || false,
    result: signingResult,
  };
}

/**
 * Load and validate save data
 */
export async function loadSaveData(saveData: string): Promise<{
  publicKey: string;
  ethereumAddress: string;
}> {
  await initTSSWasm();

  const result = tssLoadSaveData(saveData);

  if (!result.success) {
    throw new Error(result.error || 'Failed to load save data');
  }

  return {
    publicKey: result.public_key || '',
    ethereumAddress: result.ethereum_address || '',
  };
}

/**
 * Clean up a session
 */
export async function cleanupSession(sessionId: string): Promise<void> {
  if (!wasmInitialized) {
    return;
  }

  tssCleanupSession(sessionId);
}

// =========================================================================
// Helper Functions
// =========================================================================

/**
 * Load a script dynamically
 */
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

/**
 * Wait for a global function to be defined
 */
function waitForGlobalFunction(name: string, timeoutMs: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();

    const check = () => {
      if (typeof (window as any)[name] === 'function') {
        resolve();
      } else if (Date.now() - start > timeoutMs) {
        reject(new Error(`Timeout waiting for ${name}`));
      } else {
        setTimeout(check, 50);
      }
    };

    check();
  });
}

/**
 * Keccak256 hash (for Ethereum address calculation)
 * Uses js-sha3 library
 */
function keccak256Hex(dataHex: string): string {
  const bytes = hexToBytes(dataHex);
  return keccak_256(bytes);
}

/**
 * Convert hex string to Uint8Array
 */
function hexToBytes(hex: string): Uint8Array {
  if (hex.startsWith('0x')) {
    hex = hex.slice(2);
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}
