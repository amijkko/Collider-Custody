/**
 * MPC WebSocket Client for browser-side MPC participation.
 *
 * This client handles communication with the MPC Coordinator via WebSocket
 * for both DKG (key generation) and signing operations.
 *
 * Uses the Go tss-lib compiled to WASM for cryptographic operations.
 */

import * as storage from './storage';
import * as tssWasm from './wasm/tss-wasm';

export interface DKGResult {
  keysetId: string;
  ethereumAddress: string;
  publicKey: string;
  userShare: string; // Hex-encoded save data for storage
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
  | 'initializing_wasm'
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
  private currentWalletId: string | null = null;

  // For round handling
  private partyIndex: number = 1; // User is always party 1
  private threshold: number = 1;
  private totalParties: number = 2;

  // TSS state
  private dkgSaveData: string | null = null;
  private currentSigningSaveData: string | null = null;
  private currentMessageHash: string | null = null;

  // Heartbeat
  private pingInterval: ReturnType<typeof setInterval> | null = null;

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
   * Initialize WASM module (can be called ahead of time)
   */
  async initializeWasm(): Promise<void> {
    if (tssWasm.isWasmInitialized()) {
      return;
    }

    this.setStatus('initializing_wasm');
    try {
      await tssWasm.initTSSWasm();
      console.log('[MPC] TSS WASM initialized');
    } catch (error) {
      console.error('[MPC] Failed to initialize WASM:', error);
      throw error;
    }
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
        data: { token: this.config.token },
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

    // Initialize WASM if not already done
    await this.initializeWasm();

    this.currentPassword = password;
    this.currentWalletId = walletId;
    this.setStatus('dkg_in_progress');

    return new Promise((resolve, reject) => {
      this.dkgPromise = { resolve, reject };

      this.send({
        type: 'dkg_start',
        data: { wallet_id: walletId },
      });

      // Timeout (DKG can take a while - pre-params generation takes 10-30 sec)
      setTimeout(() => {
        if (this.dkgPromise) {
          this.dkgPromise.reject(new Error('DKG timeout'));
          this.dkgPromise = null;
          this.setStatus('authenticated');
          this.cleanupDKGSession();
        }
      }, 300000); // 5 minutes
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

    // Initialize WASM if not already done
    await this.initializeWasm();

    // Load and decrypt share
    const share = await storage.getShare(keysetId);
    if (!share) {
      throw new Error('Share not found for keyset');
    }

    // Verify password by attempting to decrypt share
    const { decryptShare } = await import('./crypto');
    let saveData: Uint8Array;
    try {
      saveData = await decryptShare(share, password);
      this.currentPassword = password;
      this.currentSigningSaveData = bytesToHex(saveData);
      // Remove 0x prefix for WASM (expects raw hex)
      this.currentMessageHash = messageHash.startsWith('0x') ? messageHash.slice(2) : messageHash;
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
        },
      });

      // Timeout
      setTimeout(() => {
        if (this.signingPromise) {
          this.signingPromise.reject(new Error('Signing timeout'));
          this.signingPromise = null;
          this.setStatus('authenticated');
          this.cleanupSigningSession();
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
    // Log with full details for errors, minimal for others
    if (message.type.includes('error') || message.type === 'error') {
      console.error('[MPC] Error received:', message.type, {
        session_id: message.session_id,
        error: message.data?.error,
        details: message.data,
      });
    } else {
      console.log('[MPC] Received:', message.type, message.session_id || '');
    }

    switch (message.type) {
      case 'auth_ok':
        this.handleAuthOk();
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

  private handleAuthOk(): void {
    this.setStatus('authenticated');
    this.authPromise?.resolve();
    this.authPromise = null;
  }

  private handleAuthError(message: WebSocketMessage): void {
    const errorMsg = (message.data?.error as string) || 'Authentication failed';
    console.error('[MPC] Auth error:', errorMsg, message.data);
    const error = new Error(errorMsg);
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

    console.log(
      `[MPC] DKG Round ${round}, bank message:`,
      bankMessage ? 'yes' : 'no'
    );
    this.config.onProgress?.(`DKG Round ${round}`, round, 3);

    try {
      let userMessage: string;

      if (round === 1) {
        // Start DKG session in WASM
        const startResult = await tssWasm.startDKG(
          this.currentSessionId!,
          this.partyIndex,
          this.threshold,
          this.totalParties
        );

        // Collect all message objects to send
        // Each message is an object like {ToPartyIndex, IsBroadcast, Payload}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const messagesToSend: any[] = [];

        // Parse round1Msg if it's a JSON array string
        if (startResult.round1Msg) {
          if (startResult.round1Msg.startsWith('[')) {
            try {
              const msgs = JSON.parse(startResult.round1Msg);
              messagesToSend.push(...msgs);
              console.log(`[MPC] Parsed ${msgs.length} messages from round1Msg`);
            } catch {
              // If not valid JSON array, just keep as-is (should not happen)
              console.warn('[MPC] round1Msg is not valid JSON array');
            }
          }
        }

        // Also process the incoming bank message from round 1
        if (bankMessage) {
          console.log('[MPC] Processing bank round 1 message after startDKG');
          const incomingMessages: tssWasm.IncomingMessage[] = [
            { from_party: 0, payload: bankMessage },
          ];
          const processResult = await tssWasm.processDKGRound(
            this.currentSessionId!,
            1,
            incomingMessages
          );

          // If there are outgoing messages from processing, add them
          if (processResult.outgoingMsg) {
            console.log('[MPC] Got additional outgoing message from processing bank round 1, size:', processResult.outgoingMsg.length);
            // Parse outgoingMsg JSON array and add objects
            if (processResult.outgoingMsg.startsWith('[')) {
              try {
                const msgArray = JSON.parse(processResult.outgoingMsg);
                messagesToSend.push(...msgArray);
                console.log(`[MPC] Unpacked ${msgArray.length} messages from processResult`);
              } catch {
                console.warn('[MPC] Failed to parse outgoingMsg as JSON array');
              }
            }
          }

          // Check if DKG completed after processing bank's round 1
          if (processResult.isFinal && processResult.result) {
            this.dkgSaveData = processResult.result.save_data;
            console.log('[MPC] Local DKG completed after processing bank round 1');
          }
        }

        // Always send as JSON array of message objects
        if (messagesToSend.length > 0) {
          userMessage = JSON.stringify(messagesToSend);
          console.log(`[MPC] Sending ${messagesToSend.length} messages as JSON array`);
        } else {
          userMessage = '';
        }
      } else {
        // Process incoming bank message
        const incomingMessages: tssWasm.IncomingMessage[] = bankMessage
          ? [{ from_party: 0, payload: bankMessage }]
          : [];

        const result = await tssWasm.processDKGRound(
          this.currentSessionId!,
          round,
          incomingMessages
        );

        if (result.isFinal && result.result) {
          // DKG completed locally - store save data
          this.dkgSaveData = result.result.save_data;
          console.log('[MPC] Local DKG complete, waiting for server confirmation');
        }

        // outgoingMsg can be single hex string or JSON array of hex strings
        userMessage = result.outgoingMsg;
      }

      // Send response to server
      this.send({
        type: 'dkg_round',
        session_id: this.currentSessionId || undefined,
        data: {
          round: round,
          user_message: userMessage,
        },
      });
    } catch (error) {
      console.error('[MPC] DKG round error:', error);
      this.dkgPromise?.reject(
        error instanceof Error ? error : new Error(String(error))
      );
      this.dkgPromise = null;
      this.setStatus('authenticated');
      this.cleanupDKGSession();
    }
  }

  private async handleDKGComplete(message: WebSocketMessage): Promise<void> {
    const data = message.data || {};

    const result: DKGResult = {
      keysetId: data.keyset_id as string,
      ethereumAddress: data.ethereum_address as string,
      publicKey: data.public_key as string,
      userShare: this.dkgSaveData || '', // Use locally computed save data
    };

    // Save encrypted share
    if (this.currentPassword && result.userShare) {
      try {
        const { encryptShare } = await import('./crypto');
        const shareBytes = hexToBytes(result.userShare);
        const encrypted = await encryptShare(
          shareBytes,
          this.currentPassword,
          this.currentWalletId || '',
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
    this.cleanupDKGSession();
  }

  private handleDKGError(message: WebSocketMessage): void {
    const errorMsg = (message.data?.error as string) || 'DKG failed';
    console.error('[MPC] DKG error:', errorMsg, message.data);
    const error = new Error(errorMsg);
    this.setStatus('authenticated');
    this.dkgPromise?.reject(error);
    this.dkgPromise = null;
    this.cleanupDKGSession();
  }

  private async handleSignRound(message: WebSocketMessage): Promise<void> {
    const data = message.data || {};
    const round = data.round as number;
    const bankMessage = data.bank_message as string | null;

    if (message.session_id) {
      this.currentSessionId = message.session_id;
    }

    console.log(
      `[MPC] Sign Round ${round}, bank message:`,
      bankMessage ? 'yes' : 'no'
    );
    this.config.onProgress?.(`Signing Round ${round}`, round, 9);

    try {
      let userMessage: string;

      if (round === 1) {
        // Start signing session in WASM
        const result = await tssWasm.startSigning(
          this.currentSessionId!,
          this.partyIndex,
          this.currentMessageHash!,
          this.currentSigningSaveData!,
          this.totalParties,
          this.threshold
        );
        userMessage = result.round1Msg;
      } else {
        // Process incoming bank message
        const incomingMessages: tssWasm.IncomingMessage[] = bankMessage
          ? [{ from_party: 0, payload: bankMessage }]
          : [];

        const result = await tssWasm.processSigningRound(
          this.currentSessionId!,
          round,
          incomingMessages
        );

        if (result.isFinal && result.result) {
          // Signing completed locally
          console.log('[MPC] Local signing complete');
        }

        userMessage = result.outgoingMsg;
      }

      // Send response to server
      this.send({
        type: 'sign_round',
        session_id: this.currentSessionId || undefined,
        data: {
          round: round,
          user_message: userMessage,
        },
      });
    } catch (error) {
      console.error('[MPC] Signing round error:', error);
      this.signingPromise?.reject(
        error instanceof Error ? error : new Error(String(error))
      );
      this.signingPromise = null;
      this.setStatus('authenticated');
      this.cleanupSigningSession();
    }
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
    this.cleanupSigningSession();
  }

  private handleSignError(message: WebSocketMessage): void {
    const errorMsg = (message.data?.error as string) || 'Signing failed';
    console.error('[MPC] Signing error:', errorMsg, message.data);
    const error = new Error(errorMsg);
    this.setStatus('authenticated');
    this.signingPromise?.reject(error);
    this.signingPromise = null;
    this.cleanupSigningSession();
  }

  private handleError(message: WebSocketMessage): void {
    const errorMsg = (message.data?.error as string) || 'Unknown error';
    console.error('[MPC] General error:', errorMsg, message.data);
    const error = new Error(errorMsg);
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
    this.cleanupDKGSession();
    this.cleanupSigningSession();
  }

  private cleanupDKGSession(): void {
    if (this.currentSessionId) {
      tssWasm.cleanupSession(this.currentSessionId).catch(() => {});
    }
    this.currentPassword = null;
    this.currentWalletId = null;
    this.currentSessionId = null;
    this.dkgSaveData = null;
  }

  private cleanupSigningSession(): void {
    if (this.currentSessionId) {
      tssWasm.cleanupSession(this.currentSessionId).catch(() => {});
    }
    this.currentPassword = null;
    this.currentSessionId = null;
    this.currentSigningSaveData = null;
    this.currentMessageHash = null;
  }
}

// =========================================================================
// Utility Functions
// =========================================================================

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

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

/**
 * Factory function to create an MPC client instance
 */
export function createMPCClient(config: MPCClientConfig): MPCClient {
  return new MPCClient(config);
}

/**
 * Pre-initialize WASM module (call on app startup)
 */
export async function preloadTSSWasm(): Promise<void> {
  await tssWasm.initTSSWasm();
}
