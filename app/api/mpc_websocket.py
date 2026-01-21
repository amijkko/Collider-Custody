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
    ):
        self.session_id = session_id
        self.session_type = session_type
        self.user_id = user_id
        self.wallet_id = wallet_id
        self.keyset_id = keyset_id
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
    ) -> MPCSession:
        session_id = str(uuid4())
        session = MPCSession(
            session_id=session_id,
            session_type=session_type,
            user_id=user_id,
            wallet_id=wallet_id,
            keyset_id=keyset_id,
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
    user_message = data.get("user_message")
    
    if user_message:
        user_message = bytes.fromhex(user_message)
    
    try:
        # Process round on bank signer
        success, out_msg, result, is_final, error = await mpc_client.process_dkg_round(
            session_id=session_id,
            round_num=round_num,
            incoming_messages=[user_message] if user_message else [],
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
                "public_key": result.public_key.hex(),
            }
            session.keyset_id = result.keyset_id
            
            await websocket.send_json({
                "type": MessageType.DKG_COMPLETE,
                "session_id": session_id,
                "data": {
                    "keyset_id": result.keyset_id,
                    "ethereum_address": result.ethereum_address,
                    "public_key": result.public_key.hex(),
                    "user_share": result.user_share.hex() if result.user_share else None,
                }
            })
            
            logger.info(f"DKG complete for session {session_id}: {result.ethereum_address}")
            
            # Don't cleanup immediately - let coordinator update DB
            # manager.cleanup_session(session_id)
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
    
    message_hash_bytes = bytes.fromhex(message_hash)
    
    # Create session
    session = manager.create_session(
        session_type="signing",
        user_id=user_id,
        keyset_id=keyset_id,
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
                "data": {"error": error}
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
            "data": {"error": str(e)}
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
    user_message = data.get("user_message")
    
    if user_message:
        user_message = bytes.fromhex(user_message)
    
    try:
        # Process round on bank signer
        success, out_msg, result, is_final, error = await mpc_client.process_signing_round(
            session_id=session_id,
            round_num=round_num,
            incoming_messages=[user_message] if user_message else [],
        )
        
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
            
            await websocket.send_json({
                "type": MessageType.SIGN_COMPLETE,
                "session_id": session_id,
                "data": session.result,
            })
            
            logger.info(f"Signing complete for session {session_id}")
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
            "data": {"error": str(e)}
        })
        manager.cleanup_session(session_id)
