/**
 * MPC WebSocket Client for browser-side MPC participation.
 * 
 * This client handles communication with the MPC Coordinator via WebSocket
 * for both DKG (key generation) and signing operations.
 */

import * as storage from './storage';
import { EncryptedShare } from './crypto';

export interface DKGResult {
  keysetId: string;
  ethereumAddress: string;
  publicKey: string;
  userShare: string; // Hex-encoded encrypted share
}

export interface SigningResult {
  signatureR: string;
  signatureS: string;
  signatureV: number;
  fullSignature: string;
}

export type MessageType = 
  | 'auth'
  | 'auth_ok'
  | 'auth_error'
  | 'dkg_start'
  | 'dkg_round'
  | 'dkg_complete'
  | 'dkg_error'
  | 'sign_start'
  | 'sign_round'
  | 'sign_complete'
  | 'sign_error'
  | 'error'
  | 'ping'
  | 'pong';

export interface WebSocketMessage {
  type: MessageType;
  session_id?: string;
  data?: Record<string, unknown>;
}

export interface MPCClientConfig {
  wsUrl: string;
  token?: string;
  onStatusChange?: (status: MPCStatus) => void;
  onError?: (error: Error) => void;
  onProgress?: (message: string, round: number, total: number) => void;
}

export type MPCStatus = 
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'authenticating'
  | 'authenticated'
  | 'dkg_in_progress'
  | 'signing_in_progress'
  | 'error';

/**
 * MPC WebSocket Client
 * 
 * Handles the browser's participation in MPC protocols:
 * - Connects to the MPC Coordinator via WebSocket
 * - Participates in DKG as party 1 (user)
 * - Participates in signing as party 1
 * - Stores encrypted shares in IndexedDB
 */
export class MPCClient {
  private ws: WebSocket | null = null;
  private config: MPCClientConfig;
  private status: MPCStatus = 'disconnected';
  // Storage and crypto utilities
  
  // Pending promises for async operations
  private authPromise: {
    resolve: (value: void) => void;
    reject: (reason: Error) => void;
  } | null = null;
  
  private dkgPromise: {
    resolve: (value: DKGResult) => void;
    reject: (reason: Error) => void;
  } | null = null;
  
  private signingPromise: {
    resolve: (value: SigningResult) => void;
    reject: (reason: Error) => void;
  } | null = null;
  
  private currentSessionId: string | null = null;
  private currentPassword: string | null = null;
  
  // For round handling
  private partyIndex: number = 1; // User is always party 1
  private threshold: number = 1;
  private totalParties: number = 2;
  
  // Heartbeat
  private pingInterval: NodeJS.Timeout | null = null;
  
  constructor(config: MPCClientConfig) {
    this.config = config;
  }
  
  /**
   * Current connection status
   */
  getStatus(): MPCStatus {
    return this.status;
  }
  
  /**
   * Connect to the MPC Coordinator WebSocket
   */
  async connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }
    
    this.setStatus('connecting');
    
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.config.wsUrl);
        
        this.ws.onopen = () => {
          console.log('[MPC] WebSocket connected');
          this.setStatus('connected');
          this.startHeartbeat();
          resolve();
        };
        
        this.ws.onclose = (event) => {
          console.log('[MPC] WebSocket closed:', event.code, event.reason);
          this.setStatus('disconnected');
          this.stopHeartbeat();
          this.cleanup();
        };
        
        this.ws.onerror = (error) => {
          console.error('[MPC] WebSocket error:', error);
          this.setStatus('error');
          this.config.onError?.(new Error('WebSocket connection error'));
          reject(new Error('WebSocket connection failed'));
        };
        
        this.ws.onmessage = (event) => {
          this.handleMessage(JSON.parse(event.data));
        };
        
      } catch (error) {
        this.setStatus('error');
        reject(error);
      }
    });
  }
  
  /**
   * Authenticate with the server
   */
  async authenticate(): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }
    
    this.setStatus('authenticating');
    
    return new Promise((resolve, reject) => {
      this.authPromise = { resolve, reject };
      
      this.send({
        type: 'auth',
        data: { token: this.config.token }
      });
      
      // Timeout
      setTimeout(() => {
        if (this.authPromise) {
          this.authPromise.reject(new Error('Authentication timeout'));
          this.authPromise = null;
        }
      }, 10000);
    });
  }
  
  /**
   * Start DKG (Distributed Key Generation)
   * 
   * @param walletId - The wallet ID to associate with the generated key
   * @param password - Password for encrypting the user's share
   * @returns DKG result with keyset ID and Ethereum address
   */
  async startDKG(walletId: string, password: string): Promise<DKGResult> {
    if (this.status !== 'authenticated') {
      throw new Error('Not authenticated');
    }
    
    this.currentPassword = password;
    this.setStatus('dkg_in_progress');
    
    return new Promise((resolve, reject) => {
      this.dkgPromise = { resolve, reject };
      
      this.send({
        type: 'dkg_start',
        data: { wallet_id: walletId }
      });
      
      // Timeout (DKG can take a while)
      setTimeout(() => {
        if (this.dkgPromise) {
          this.dkgPromise.reject(new Error('DKG timeout'));
          this.dkgPromise = null;
          this.setStatus('authenticated');
        }
      }, 120000); // 2 minutes
    });
  }
  
  /**
   * Start MPC Signing
   * 
   * @param keysetId - The keyset ID to use for signing
   * @param txRequestId - The transaction request ID
   * @param messageHash - The 32-byte message hash to sign (hex)
   * @param password - Password to decrypt the user's share
   * @returns Signature result
   */
  async startSigning(
    keysetId: string,
    txRequestId: string,
    messageHash: string,
    walletId: string,
    password: string
  ): Promise<SigningResult> {
    if (this.status !== 'authenticated') {
      throw new Error('Not authenticated');
    }
    
    // Load and decrypt share
    const share = await storage.getShare(keysetId);
    if (!share) {
      throw new Error('Share not found for keyset');
    }
    
    // Verify password by attempting to decrypt share
    // Import decrypt function from crypto module
    const { decryptShare } = await import('./crypto');
    try {
      await decryptShare(share, password);
      this.currentPassword = password;
    } catch {
      throw new Error('Invalid password');
    }
    
    this.setStatus('signing_in_progress');
    
    return new Promise((resolve, reject) => {
      this.signingPromise = { resolve, reject };
      
      this.send({
        type: 'sign_start',
        data: {
          keyset_id: keysetId,
          tx_request_id: txRequestId,
          message_hash: messageHash,
          wallet_id: walletId,
        }
      });
      
      // Timeout
      setTimeout(() => {
        if (this.signingPromise) {
          this.signingPromise.reject(new Error('Signing timeout'));
          this.signingPromise = null;
          this.setStatus('authenticated');
        }
      }, 120000);
    });
  }
  
  /**
   * Disconnect from the WebSocket
   */
  disconnect(): void {
    this.stopHeartbeat();
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.cleanup();
    this.setStatus('disconnected');
  }
  
  // =========================================================================
  // Private Methods
  // =========================================================================
  
  private setStatus(status: MPCStatus): void {
    this.status = status;
    this.config.onStatusChange?.(status);
  }
  
  private send(message: WebSocketMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }
  
  private handleMessage(message: WebSocketMessage): void {
    console.log('[MPC] Received:', message.type, message.session_id);
    
    switch (message.type) {
      case 'auth_ok':
        this.handleAuthOk(message);
        break;
      case 'auth_error':
        this.handleAuthError(message);
        break;
      case 'dkg_round':
        this.handleDKGRound(message);
        break;
      case 'dkg_complete':
        this.handleDKGComplete(message);
        break;
      case 'dkg_error':
        this.handleDKGError(message);
        break;
      case 'sign_round':
        this.handleSignRound(message);
        break;
      case 'sign_complete':
        this.handleSignComplete(message);
        break;
      case 'sign_error':
        this.handleSignError(message);
        break;
      case 'pong':
        // Heartbeat response
        break;
      case 'error':
        this.handleError(message);
        break;
    }
  }
  
  private handleAuthOk(message: WebSocketMessage): void {
    this.setStatus('authenticated');
    this.authPromise?.resolve();
    this.authPromise = null;
  }
  
  private handleAuthError(message: WebSocketMessage): void {
    const error = new Error(message.data?.error as string || 'Authentication failed');
    this.setStatus('error');
    this.authPromise?.reject(error);
    this.authPromise = null;
  }
  
  private async handleDKGRound(message: WebSocketMessage): Promise<void> {
    const data = message.data || {};
    const round = data.round as number;
    const bankMessage = data.bank_message as string | null;
    
    // Store session ID
    if (message.session_id) {
      this.currentSessionId = message.session_id;
    }
    
    // Get parameters from first round
    if (round === 1) {
      this.partyIndex = (data.party_index as number) || 1;
      this.threshold = (data.threshold as number) || 1;
      this.totalParties = (data.total_parties as number) || 2;
    }
    
    console.log(`[MPC] DKG Round ${round}, bank message:`, bankMessage ? 'yes' : 'no');
    
    // Simulate user's round computation
    // In real implementation, this would use WASM tss-lib
    await this.simulateComputation(100);
    
    // Generate user's response message
    const userMessage = this.generateSimulatedMessage();
    
    // Send response
    this.send({
      type: 'dkg_round',
      session_id: this.currentSessionId || undefined,
      data: {
        round: round,
        user_message: userMessage,
      }
    });
  }
  
  private async handleDKGComplete(message: WebSocketMessage): Promise<void> {
    const data = message.data || {};
    
    const result: DKGResult = {
      keysetId: data.keyset_id as string,
      ethereumAddress: data.ethereum_address as string,
      publicKey: data.public_key as string,
      userShare: data.user_share as string,
    };
    
    // Save encrypted share
    if (this.currentPassword && result.userShare) {
      try {
        const { encryptShare } = await import('./crypto');
        const shareBytes = hexToBytes(result.userShare);
        const encrypted = await encryptShare(
          shareBytes,
          this.currentPassword,
          '', // walletId will be set by caller
          result.keysetId,
          result.publicKey,
          result.ethereumAddress
        );
        
        await storage.saveShare(encrypted);
        
        console.log('[MPC] Share saved to IndexedDB');
      } catch (e) {
        console.error('[MPC] Failed to save share:', e);
      }
    }
    
    this.setStatus('authenticated');
    this.dkgPromise?.resolve(result);
    this.dkgPromise = null;
    this.currentPassword = null;
    this.currentSessionId = null;
  }
  
  private handleDKGError(message: WebSocketMessage): void {
    const error = new Error(message.data?.error as string || 'DKG failed');
    this.setStatus('authenticated');
    this.dkgPromise?.reject(error);
    this.dkgPromise = null;
    this.currentPassword = null;
  }
  
  private async handleSignRound(message: WebSocketMessage): Promise<void> {
    const data = message.data || {};
    const round = data.round as number;
    const bankMessage = data.bank_message as string | null;
    
    if (message.session_id) {
      this.currentSessionId = message.session_id;
    }
    
    console.log(`[MPC] Sign Round ${round}, bank message:`, bankMessage ? 'yes' : 'no');
    
    // Simulate computation
    await this.simulateComputation(50);
    
    // Generate response
    const userMessage = this.generateSimulatedMessage();
    
    this.send({
      type: 'sign_round',
      session_id: this.currentSessionId || undefined,
      data: {
        round: round,
        user_message: userMessage,
      }
    });
  }
  
  private handleSignComplete(message: WebSocketMessage): void {
    const data = message.data || {};
    
    const result: SigningResult = {
      signatureR: data.signature_r as string,
      signatureS: data.signature_s as string,
      signatureV: data.signature_v as number,
      fullSignature: data.full_signature as string,
    };
    
    this.setStatus('authenticated');
    this.signingPromise?.resolve(result);
    this.signingPromise = null;
    this.currentPassword = null;
    this.currentSessionId = null;
  }
  
  private handleSignError(message: WebSocketMessage): void {
    const error = new Error(message.data?.error as string || 'Signing failed');
    this.setStatus('authenticated');
    this.signingPromise?.reject(error);
    this.signingPromise = null;
    this.currentPassword = null;
  }
  
  private handleError(message: WebSocketMessage): void {
    const error = new Error(message.data?.error as string || 'Unknown error');
    this.config.onError?.(error);
  }
  
  private startHeartbeat(): void {
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping' });
    }, 30000);
  }
  
  private stopHeartbeat(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
  
  private cleanup(): void {
    if (this.authPromise) {
      this.authPromise.reject(new Error('Connection closed'));
      this.authPromise = null;
    }
    if (this.dkgPromise) {
      this.dkgPromise.reject(new Error('Connection closed'));
      this.dkgPromise = null;
    }
    if (this.signingPromise) {
      this.signingPromise.reject(new Error('Connection closed'));
      this.signingPromise = null;
    }
    this.currentPassword = null;
    this.currentSessionId = null;
  }
  
  // =========================================================================
  // Simulation Helpers (will be replaced with real tss-lib WASM)
  // =========================================================================
  
  private async simulateComputation(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
  
  private generateSimulatedMessage(): string {
    // Generate random bytes as simulated MPC message
    const bytes = new Uint8Array(64);
    crypto.getRandomValues(bytes);
    return bytesToHex(bytes);
  }
}

// =========================================================================
// Utility Functions
// =========================================================================

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

/**
 * Factory function to create an MPC client instance
 */
export function createMPCClient(config: MPCClientConfig): MPCClient {
  return new MPCClient(config);
}
