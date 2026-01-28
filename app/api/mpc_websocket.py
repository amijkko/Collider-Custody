"""
WebSocket endpoint for MPC protocol communication with browser clients.

This module handles real-time bidirectional communication between the
browser MPC client and the MPC Coordinator during DKG and signing operations.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from uuid import uuid4
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.websockets import WebSocketState
from pydantic import BaseModel

from app.services.mpc_grpc_client import (
    get_mpc_signer_client,
    MPCSignerClient,
    DKGResult,
    SigningResult,
    SigningPermit,
)
from app.api.deps import get_current_user_ws
from app.models.user import User
from app.database import async_session_maker
from app.services.wallet import WalletService
from app.services.audit import AuditService
from app.services.ethereum import EthereumService
from app.models.tx_request import TxRequest, TxStatus
from app.models.wallet import Wallet
from sqlalchemy import select
from eth_account import Account
from web3 import Web3
import rlp
from eth_utils import to_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/mpc/ws", tags=["MPC WebSocket"])


class MessageType(str, Enum):
    """WebSocket message types."""
    # Auth
    AUTH = "auth"
    AUTH_OK = "auth_ok"
    AUTH_ERROR = "auth_error"
    
    # DKG
    DKG_START = "dkg_start"
    DKG_ROUND = "dkg_round"
    DKG_COMPLETE = "dkg_complete"
    DKG_ERROR = "dkg_error"
    
    # Signing
    SIGN_START = "sign_start"
    SIGN_ROUND = "sign_round"
    SIGN_COMPLETE = "sign_complete"
    SIGN_ERROR = "sign_error"
    
    # General
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class WebSocketMessage(BaseModel):
    """Base WebSocket message."""
    type: str
    session_id: Optional[str] = None
    data: Optional[dict] = None


class MPCSession:
    """Tracks an active MPC session."""
    def __init__(
        self,
        session_id: str,
        session_type: str,  # "dkg" or "signing"
        user_id: str,
        wallet_id: Optional[str] = None,
        keyset_id: Optional[str] = None,
        tx_request_id: Optional[str] = None,
    ):
        self.session_id = session_id
        self.session_type = session_type
        self.user_id = user_id
        self.wallet_id = wallet_id
        self.keyset_id = keyset_id
        self.tx_request_id = tx_request_id
        self.current_round = 0
        self.created_at = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(minutes=5)
        self.bank_messages: asyncio.Queue = asyncio.Queue()
        self.user_messages: asyncio.Queue = asyncio.Queue()
        self.completed = False
        self.result: Optional[dict] = None


class ConnectionManager:
    """Manages WebSocket connections and MPC sessions."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # user_id -> WebSocket
        self.sessions: Dict[str, MPCSession] = {}  # session_id -> MPCSession
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        async with self._lock:
            # Close existing connection if any
            if user_id in self.active_connections:
                old_ws = self.active_connections[user_id]
                try:
                    await old_ws.close()
                except:
                    pass
            self.active_connections[user_id] = websocket
        logger.info(f"User {user_id} connected via WebSocket")
    
    async def disconnect(self, user_id: str):
        async with self._lock:
            if user_id in self.active_connections:
                del self.active_connections[user_id]
        logger.info(f"User {user_id} disconnected")
    
    async def send_message(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            ws = self.active_connections[user_id]
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_json(message)
    
    def create_session(
        self,
        session_type: str,
        user_id: str,
        wallet_id: Optional[str] = None,
        keyset_id: Optional[str] = None,
        tx_request_id: Optional[str] = None,
    ) -> MPCSession:
        session_id = str(uuid4())
        session = MPCSession(
            session_id=session_id,
            session_type=session_type,
            user_id=user_id,
            wallet_id=wallet_id,
            keyset_id=keyset_id,
            tx_request_id=tx_request_id,
        )
        self.sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[MPCSession]:
        return self.sessions.get(session_id)
    
    def cleanup_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]


# Global connection manager
manager = ConnectionManager()


@router.websocket("")
async def mpc_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for MPC protocol communication.
    
    Authentication is done via the first message containing JWT token.
    
    Message format:
    {
        "type": "auth|dkg_start|dkg_round|sign_start|sign_round|ping",
        "session_id": "optional-session-id",
        "data": { ... }
    }
    """
    user_id: Optional[str] = None
    
    try:
        await websocket.accept()
        
        # Wait for auth message
        try:
            auth_msg = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            await websocket.send_json({
                "type": MessageType.AUTH_ERROR,
                "data": {"error": "Authentication timeout"}
            })
            await websocket.close()
            return
        
        if auth_msg.get("type") != MessageType.AUTH:
            await websocket.send_json({
                "type": MessageType.AUTH_ERROR,
                "data": {"error": "First message must be auth"}
            })
            await websocket.close()
            return
        
        # Validate token
        token = auth_msg.get("data", {}).get("token")
        if not token:
            await websocket.send_json({
                "type": MessageType.AUTH_ERROR,
                "data": {"error": "Token required"}
            })
            await websocket.close()
            return
        
        try:
            user = await get_current_user_ws(token)
            user_id = str(user.id)
        except Exception as e:
            await websocket.send_json({
                "type": MessageType.AUTH_ERROR,
                "data": {"error": str(e)}
            })
            await websocket.close()
            return
        
        # Register connection
        manager.active_connections[user_id] = websocket
        
        await websocket.send_json({
            "type": MessageType.AUTH_OK,
            "data": {"user_id": user_id}
        })
        
        logger.info(f"User {user_id} authenticated via WebSocket")
        
        # Get MPC client
        mpc_client = get_mpc_signer_client()
        
        # Main message loop
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                session_id = message.get("session_id")
                data = message.get("data", {})
                
                if msg_type == MessageType.PING:
                    await websocket.send_json({"type": MessageType.PONG})
                
                elif msg_type == MessageType.DKG_START:
                    await handle_dkg_start(
                        websocket, user_id, data, mpc_client
                    )
                
                elif msg_type == MessageType.DKG_ROUND:
                    await handle_dkg_round(
                        websocket, user_id, session_id, data, mpc_client
                    )
                
                elif msg_type == MessageType.SIGN_START:
                    await handle_sign_start(
                        websocket, user_id, data, mpc_client
                    )
                
                elif msg_type == MessageType.SIGN_ROUND:
                    await handle_sign_round(
                        websocket, user_id, session_id, data, mpc_client
                    )
                
                else:
                    await websocket.send_json({
                        "type": MessageType.ERROR,
                        "data": {"error": f"Unknown message type: {msg_type}"}
                    })
                    
            except WebSocketDisconnect:
                raise
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": MessageType.ERROR,
                    "data": {"error": "Invalid JSON"}
                })
            except Exception as e:
                logger.exception(f"Error handling message: {e}")
                await websocket.send_json({
                    "type": MessageType.ERROR,
                    "data": {"error": str(e)}
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
    finally:
        if user_id:
            await manager.disconnect(user_id)


async def _finalize_signing(
    session: MPCSession,
    result: SigningResult,
    user_id: str,
):
    """
    Finalize MPC signing: save signature to DB, update status, and broadcast transaction.

    This function:
    1. Retrieves the transaction from DB
    2. Assembles the signed transaction from R, S, V components
    3. Saves signed_tx and tx_hash to DB
    4. Updates transaction status to SIGNED -> BROADCAST_PENDING -> BROADCASTED
    5. Broadcasts the transaction to Ethereum network
    """
    if not session.tx_request_id:
        raise ValueError("tx_request_id not found in session")

    # Get DB session
    async with async_session_maker() as db:
        # Get transaction
        tx_result = await db.execute(
            select(TxRequest).where(TxRequest.id == session.tx_request_id)
        )
        tx = tx_result.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {session.tx_request_id} not found")

        # Get wallet
        wallet_result = await db.execute(
            select(Wallet).where(Wallet.id == tx.wallet_id)
        )
        wallet = wallet_result.scalar_one_or_none()
        if not wallet:
            raise ValueError(f"Wallet {tx.wallet_id} not found")

        # Create ethereum service
        audit_service = AuditService(db)
        ethereum_service = EthereumService(db, audit_service)

        # Build transaction dict to assemble signed transaction
        from decimal import Decimal

        # Convert Decimal/str to int safely
        if tx.asset == "ETH":
            try:
                value_wei = int(tx.amount)
            except (TypeError, ValueError):
                value_wei = int(Decimal(str(tx.amount)))
        else:
            value_wei = 0

        gas_prices = await ethereum_service.get_gas_price()

        # Convert gas_price from Decimal to int
        if tx.gas_price is not None:
            try:
                gas_price = int(tx.gas_price)
            except (TypeError, ValueError):
                gas_price = int(Decimal(str(tx.gas_price)))
        else:
            gas_price = int(gas_prices.get("legacy_gas_price", 20000000000))

        # Convert all numeric fields to int (they may be Decimal from DB)
        tx_dict = {
            "nonce": int(tx.nonce) if tx.nonce is not None else 0,
            "to": Web3.to_checksum_address(tx.to_address),
            "value": int(value_wei),
            "gas": int(tx.gas_limit) if tx.gas_limit is not None else 21000,
            "chainId": int(ethereum_service.chain_id),
        }

        # Use legacy transactions for now (simpler to encode with manual signature)
        # TODO: Add EIP-1559 support
        tx_dict["gasPrice"] = gas_price

        # Add data for contract calls
        if tx.data:
            tx_dict["data"] = tx.data

        # Assemble signed transaction from signature components
        # Extract R, S, V from result
        r = int.from_bytes(result.signature_r, byteorder='big')
        s = int.from_bytes(result.signature_s, byteorder='big')

        # For EIP-155: v = chainId * 2 + 35 + recovery_id
        # IMPORTANT: MPC result.signature_v is already 27 or 28 (recovery_id + 27)
        # We need to extract recovery_id first, then apply EIP-155 formula
        chain_id = int(ethereum_service.chain_id)
        recovery_id = result.signature_v - 27  # Extract recovery_id (0 or 1)
        v = chain_id * 2 + 35 + recovery_id

        logger.info(f"EIP-155 signature: chain_id={chain_id}, recovery_id={recovery_id}, v={v}, raw_v={result.signature_v}")

        # Use RLP encoding for legacy transaction
        # Legacy tx structure: [nonce, gasPrice, gas, to, value, data, v, r, s]

        # Prepare transaction fields
        nonce = tx_dict["nonce"]
        gas_price = tx_dict["gasPrice"]
        gas = tx_dict["gas"]
        to = to_bytes(hexstr=tx_dict["to"])
        value = tx_dict["value"]
        data = to_bytes(hexstr=tx_dict.get("data", "0x"))

        # Encode with RLP
        tx_list = [nonce, gas_price, gas, to, value, data, v, r, s]
        signed_tx_bytes = rlp.encode(tx_list)

        # Assemble hex strings with proper 0x prefix
        signed_tx_hex = Web3.to_hex(signed_tx_bytes)

        # Calculate transaction hash (keccak256 of signed transaction)
        tx_hash = Web3.to_hex(Web3.keccak(signed_tx_bytes))

        # Save to database (Web3.to_hex already includes 0x prefix)
        tx.signed_tx = signed_tx_hex
        tx.tx_hash = tx_hash

        # Update status to SIGNED
        if tx.status == TxStatus.SIGN_PENDING:
            tx.status = TxStatus.SIGNED

        await db.commit()

        logger.info(f"Saved signed transaction {tx.id}: tx_hash={tx.tx_hash}")

        # Broadcast transaction
        tx.status = TxStatus.BROADCAST_PENDING
        await db.commit()

        try:
            broadcast_tx_hash = await ethereum_service.broadcast_transaction(
                signed_tx_hex,
                tx.id,
                str(uuid4())  # correlation_id
            )

            tx.tx_hash = broadcast_tx_hash
            tx.status = TxStatus.BROADCASTED
            await db.commit()

            logger.info(f"Broadcasted transaction {tx.id}: tx_hash={broadcast_tx_hash}")

            # Move to confirming state
            tx.status = TxStatus.CONFIRMING
            await db.commit()

        except Exception as e:
            logger.error(f"Broadcast failed for tx {tx.id}: {e}")
            tx.status = TxStatus.FAILED_BROADCAST
            await db.commit()
            raise


async def handle_dkg_start(
    websocket: WebSocket,
    user_id: str,
    data: dict,
    mpc_client: MPCSignerClient,
):
    """Handle DKG start request from browser."""
    wallet_id = data.get("wallet_id")
    if not wallet_id:
        await websocket.send_json({
            "type": MessageType.DKG_ERROR,
            "data": {"error": "wallet_id required"}
        })
        return
    
    # Create session
    session = manager.create_session(
        session_type="dkg",
        user_id=user_id,
        wallet_id=wallet_id,
    )
    
    logger.info(f"Starting DKG session {session.session_id} for user {user_id}")
    
    try:
        # Start DKG on bank signer (party 0)
        success, bank_round1, error = await mpc_client.start_dkg(
            session_id=session.session_id,
            wallet_id=wallet_id,
            threshold=1,  # 2-of-2 threshold scheme
            total_parties=2,
            party_index=0,  # Bank is party 0
        )
        
        if not success:
            await websocket.send_json({
                "type": MessageType.DKG_ERROR,
                "session_id": session.session_id,
                "data": {"error": error}
            })
            manager.cleanup_session(session.session_id)
            return
        
        # Send bank's round 1 message to user
        await websocket.send_json({
            "type": MessageType.DKG_ROUND,
            "session_id": session.session_id,
            "data": {
                "round": 1,
                "bank_message": bank_round1.hex() if bank_round1 else None,
                "party_index": 1,  # User is party 1
                "threshold": 1,
                "total_parties": 2,
            }
        })
        
    except Exception as e:
        logger.exception(f"DKG start error: {e}")
        await websocket.send_json({
            "type": MessageType.DKG_ERROR,
            "session_id": session.session_id,
            "data": {"error": str(e)}
        })
        manager.cleanup_session(session.session_id)


async def handle_dkg_round(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    data: dict,
    mpc_client: MPCSignerClient,
):
    """Handle DKG round message from browser."""
    session = manager.get_session(session_id)
    if not session or session.user_id != user_id:
        await websocket.send_json({
            "type": MessageType.DKG_ERROR,
            "session_id": session_id,
            "data": {"error": "Session not found"}
        })
        return
    
    round_num = data.get("round", session.current_round + 1)
    user_message_raw = data.get("user_message")

    # Parse user message
    # WASM returns JSON array with metadata: [{ToPartyIndex, IsBroadcast, Payload}, ...]
    # We pass this through to bank signer which will parse the JSON
    incoming_messages = []
    if user_message_raw:
        # Check if it's the new JSON format with metadata (starts with '[{')
        if user_message_raw.startswith('[{') or user_message_raw.startswith('[{"'):
            # New format: JSON array with metadata
            # Pass the entire JSON as bytes - bank signer will parse it
            logger.info(f"DKG round {round_num}: received JSON message from user (new format)")
            incoming_messages.append((1, user_message_raw.encode('utf-8')))
        elif user_message_raw.startswith('['):
            # Old format: JSON array of hex strings
            try:
                message_list = json.loads(user_message_raw)
                logger.info(f"DKG round {round_num}: received {len(message_list)} hex messages from user (old format)")
                for msg_hex in message_list:
                    if msg_hex:
                        incoming_messages.append((1, bytes.fromhex(msg_hex)))
            except json.JSONDecodeError:
                # Not valid JSON, treat as single hex string
                incoming_messages = [(1, bytes.fromhex(user_message_raw))]
        else:
            # Single hex string
            incoming_messages = [(1, bytes.fromhex(user_message_raw))]

    try:
        # Process round on bank signer
        # User is party 1, so we include the party index
        success, out_msg, result, is_final, error = await mpc_client.process_dkg_round(
            session_id=session_id,
            round_num=round_num,
            incoming_messages=incoming_messages,
        )
        
        if not success:
            await websocket.send_json({
                "type": MessageType.DKG_ERROR,
                "session_id": session_id,
                "data": {"error": error}
            })
            manager.cleanup_session(session_id)
            return
        
        session.current_round = round_num
        
        if is_final and result:
            # DKG complete!
            session.completed = True
            session.result = {
                "keyset_id": result.keyset_id,
                "ethereum_address": result.ethereum_address,
                "public_key": result.public_key.hex() if isinstance(result.public_key, bytes) else result.public_key,
            }
            session.keyset_id = result.keyset_id

            # Save keyset and finalize wallet in database
            try:
                async with async_session_maker() as db:
                    audit = AuditService(db)
                    wallet_service = WalletService(db, audit)

                    public_key = result.public_key.hex() if isinstance(result.public_key, bytes) else result.public_key
                    public_key_full = result.public_key_full.hex() if isinstance(result.public_key_full, bytes) else result.public_key_full

                    # Derive compressed public key (first byte + x coordinate)
                    # Full key is 0x04 + x (32 bytes) + y (32 bytes) = 65 bytes
                    public_key_compressed = public_key_full  # Use full key, compression done in finalize

                    await wallet_service.finalize_mpc_wallet(
                        wallet_id=session.wallet_id,
                        keyset_id=result.keyset_id,
                        address=result.ethereum_address,
                        public_key=public_key_full,
                        public_key_compressed=public_key,
                        correlation_id=session_id,
                        actor_id=user_id,
                    )
                    await db.commit()

                logger.info(f"DKG complete and saved for session {session_id}: {result.ethereum_address}")
            except Exception as e:
                logger.exception(f"Failed to save DKG result: {e}")
                await websocket.send_json({
                    "type": MessageType.DKG_ERROR,
                    "session_id": session_id,
                    "data": {"error": f"Failed to save keyset: {str(e)}"}
                })
                manager.cleanup_session(session_id)
                return

            await websocket.send_json({
                "type": MessageType.DKG_COMPLETE,
                "session_id": session_id,
                "data": {
                    "keyset_id": result.keyset_id,
                    "ethereum_address": result.ethereum_address,
                    "public_key": result.public_key.hex() if isinstance(result.public_key, bytes) else result.public_key,
                    "public_key_full": result.public_key_full.hex() if isinstance(result.public_key_full, bytes) else result.public_key_full,
                }
            })

            manager.cleanup_session(session_id)
        else:
            # Send next round message
            await websocket.send_json({
                "type": MessageType.DKG_ROUND,
                "session_id": session_id,
                "data": {
                    "round": round_num + 1,
                    "bank_message": out_msg.hex() if out_msg else None,
                }
            })
            
    except Exception as e:
        logger.exception(f"DKG round error: {e}")
        await websocket.send_json({
            "type": MessageType.DKG_ERROR,
            "session_id": session_id,
            "data": {"error": str(e)}
        })
        manager.cleanup_session(session_id)


async def handle_sign_start(
    websocket: WebSocket,
    user_id: str,
    data: dict,
    mpc_client: MPCSignerClient,
):
    """Handle signing start request from browser."""
    keyset_id = data.get("keyset_id")
    tx_request_id = data.get("tx_request_id")
    message_hash = data.get("message_hash")
    
    if not all([keyset_id, tx_request_id, message_hash]):
        await websocket.send_json({
            "type": MessageType.SIGN_ERROR,
            "data": {"error": "keyset_id, tx_request_id, and message_hash required"}
        })
        return
    
    # Remove 0x prefix if present
    message_hash_clean = message_hash[2:] if message_hash.startswith("0x") else message_hash
    message_hash_bytes = bytes.fromhex(message_hash_clean)
    
    # Create session
    session = manager.create_session(
        session_type="signing",
        user_id=user_id,
        keyset_id=keyset_id,
        wallet_id=data.get("wallet_id"),
        tx_request_id=tx_request_id,
    )
    
    logger.info(f"Starting signing session {session.session_id} for tx {tx_request_id}")
    
    try:
        # Create permit
        permit = mpc_client.create_permit(
            tx_request_id=tx_request_id,
            wallet_id=data.get("wallet_id", ""),
            keyset_id=keyset_id,
            tx_hash=message_hash_bytes,
        )
        
        # Start signing on bank signer
        success, bank_round1, error = await mpc_client.start_signing(
            session_id=session.session_id,
            keyset_id=keyset_id,
            message_hash=message_hash_bytes,
            permit=permit,
            party_index=0,
        )
        
        if not success:
            await websocket.send_json({
                "type": MessageType.SIGN_ERROR,
                "session_id": session.session_id,
                "data": {
                    "error": error or "Bank signer failed to start signing",
                    "stage": "sign_start",
                    "keyset_id": keyset_id,
                    "tx_request_id": tx_request_id,
                }
            })
            manager.cleanup_session(session.session_id)
            return
        
        await websocket.send_json({
            "type": MessageType.SIGN_ROUND,
            "session_id": session.session_id,
            "data": {
                "round": 1,
                "bank_message": bank_round1.hex() if bank_round1 else None,
            }
        })
        
    except Exception as e:
        logger.exception(f"Signing start error: {e}")
        await websocket.send_json({
            "type": MessageType.SIGN_ERROR,
            "session_id": session.session_id,
            "data": {
                "error": f"Signing initialization failed: {str(e)}",
                "stage": "sign_start_exception",
                "keyset_id": keyset_id,
                "tx_request_id": tx_request_id,
            }
        })
        manager.cleanup_session(session.session_id)


async def handle_sign_round(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    data: dict,
    mpc_client: MPCSignerClient,
):
    """Handle signing round message from browser."""
    session = manager.get_session(session_id)
    if not session or session.user_id != user_id:
        await websocket.send_json({
            "type": MessageType.SIGN_ERROR,
            "session_id": session_id,
            "data": {"error": "Session not found"}
        })
        return
    
    round_num = data.get("round", session.current_round + 1)
    user_message_raw = data.get("user_message", "")

    logger.info(f"Sign round {round_num}: user_message_raw len={len(user_message_raw) if user_message_raw else 0}, first_chars={user_message_raw[:50] if user_message_raw else 'EMPTY'}")

    # Parse user message - WASM returns JSON array with metadata (same as DKG)
    incoming_messages = []
    if user_message_raw:
        # Check if it's JSON format with metadata (starts with '[{')
        if user_message_raw.startswith('[{') or user_message_raw.startswith('[{"'):
            # New format: JSON array with metadata
            logger.info(f"Signing round {round_num}: received JSON message from user (new format)")
            incoming_messages.append((1, user_message_raw.encode('utf-8')))
        elif user_message_raw.startswith('['):
            # Old format: JSON array of hex strings
            try:
                message_list = json.loads(user_message_raw)
                logger.info(f"Signing round {round_num}: received {len(message_list)} hex messages from user (old format)")
                for msg_hex in message_list:
                    if msg_hex:
                        incoming_messages.append((1, bytes.fromhex(msg_hex)))
            except json.JSONDecodeError:
                # Not valid JSON, treat as single hex string
                incoming_messages = [(1, bytes.fromhex(user_message_raw))]
        else:
            # Single hex string
            user_message = bytes.fromhex(user_message_raw)
            incoming_messages = [(1, user_message)]
            logger.info(f"Signing round {round_num}: single hex message, size={len(user_message)} bytes")
    else:
        logger.info(f"Signing round {round_num}: no user message (empty/no outgoing from user)")

    # Important: Always process round on bank signer, even if no incoming messages
    # The TSS protocol needs to advance on both sides
    try:

        success, out_msg, result, is_final, error = await mpc_client.process_signing_round(
            session_id=session_id,
            round_num=round_num,
            incoming_messages=incoming_messages,
        )

        logger.info(f"Signing round {round_num}: success={success}, out_msg_size={len(out_msg) if out_msg else 0}, is_final={is_final}")

        if not success:
            await websocket.send_json({
                "type": MessageType.SIGN_ERROR,
                "session_id": session_id,
                "data": {"error": error}
            })
            manager.cleanup_session(session_id)
            return
        
        session.current_round = round_num
        
        if is_final and result:
            # Signing complete!
            session.completed = True
            session.result = {
                "signature_r": result.signature_r.hex(),
                "signature_s": result.signature_s.hex(),
                "signature_v": result.signature_v,
                "full_signature": result.full_signature.hex(),
            }

            # Save signature to database and broadcast transaction
            try:
                await _finalize_signing(
                    session=session,
                    result=result,
                    user_id=user_id,
                )
                logger.info(f"Signing finalized and broadcasted for session {session_id}: R={result.signature_r.hex()[:16]}...")
            except Exception as e:
                logger.exception(f"Failed to finalize signing for session {session_id}: {e}")
                await websocket.send_json({
                    "type": MessageType.SIGN_ERROR,
                    "session_id": session_id,
                    "data": {
                        "error": f"Finalization failed: {str(e)}",
                        "stage": "finalize",
                    }
                })
                manager.cleanup_session(session_id)
                return

            await websocket.send_json({
                "type": MessageType.SIGN_COMPLETE,
                "session_id": session_id,
                "data": session.result,
            })

            logger.info(f"Signing complete for session {session_id}: R={result.signature_r.hex()[:16]}...")
        else:
            # Send next round message
            await websocket.send_json({
                "type": MessageType.SIGN_ROUND,
                "session_id": session_id,
                "data": {
                    "round": round_num + 1,
                    "bank_message": out_msg.hex() if out_msg else None,
                }
            })
            
    except Exception as e:
        logger.exception(f"Signing round error: {e}")
        await websocket.send_json({
            "type": MessageType.SIGN_ERROR,
            "session_id": session_id,
            "data": {
                "error": f"Signing round {round_num} failed: {str(e)}",
                "stage": f"sign_round_{round_num}",
                "round": round_num,
            }
        })
        manager.cleanup_session(session_id)
