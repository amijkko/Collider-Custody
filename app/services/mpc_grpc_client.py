"""
gRPC client for communicating with MPC Signer Node (Bank Node).

This module handles the communication between the MPC Coordinator
and the Bank Signer Node for DKG and signing operations.
"""
import asyncio
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple
from uuid import uuid4

# For now, we'll use a simulated gRPC client
# In production, this would use actual gRPC stubs generated from mpc.proto
# import grpc
# from proto import mpc_pb2, mpc_pb2_grpc

from app.config import get_settings

logger = logging.getLogger(__name__)

# Constants
PERMIT_SECRET = b"mpc-permit-secret-change-in-production"  # TODO: Load from env


@dataclass
class DKGResult:
    """Result of a successful DKG operation."""
    keyset_id: str
    public_key: bytes
    public_key_full: bytes
    ethereum_address: str
    user_share: bytes  # Encrypted share for user storage


@dataclass
class SigningResult:
    """Result of a successful signing operation."""
    signature_r: bytes
    signature_s: bytes
    signature_v: int
    full_signature: bytes


@dataclass
class SigningPermit:
    """Permit authorizing a signing operation."""
    tx_request_id: str
    wallet_id: str
    keyset_id: str
    tx_hash: bytes
    expires_at: int
    coordinator_signature: bytes


class MPCSignerClient:
    """
    Client for communicating with the Bank Signer Node.
    
    In production, this would use gRPC to communicate with the Go signer.
    Currently uses simulation for demonstration.
    """
    
    def __init__(self, signer_url: str = "localhost:50051"):
        self.signer_url = signer_url
        self.settings = get_settings()
        self._connected = False
        
    async def connect(self) -> bool:
        """
        Connect to the signer node.
        
        In production: establish gRPC connection
        """
        try:
            # TODO: Actual gRPC connection
            # self.channel = grpc.aio.insecure_channel(self.signer_url)
            # self.stub = mpc_pb2_grpc.MPCSignerStub(self.channel)
            self._connected = True
            logger.info(f"Connected to MPC signer at {self.signer_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MPC signer: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the signer node."""
        # TODO: Close gRPC channel
        self._connected = False
    
    async def health_check(self) -> dict:
        """Check signer node health."""
        # TODO: Call actual gRPC method
        # response = await self.stub.Health(mpc_pb2.HealthRequest())
        return {
            "healthy": True,
            "version": "1.0.0",
            "active_sessions": 0,
            "stored_keysets": 0,
        }
    
    # =========================================================================
    # DKG Operations
    # =========================================================================
    
    async def start_dkg(
        self,
        session_id: str,
        wallet_id: str,
        threshold: int,
        total_parties: int,
        party_index: int = 0,  # Bank is party 0
    ) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Start a DKG session on the bank signer.
        
        Returns:
            (success, round1_message, error)
        """
        logger.info(f"Starting DKG session {session_id} on bank signer")
        
        try:
            # TODO: Call actual gRPC method
            # request = mpc_pb2.StartDKGRequest(
            #     session_id=session_id,
            #     wallet_id=wallet_id,
            #     threshold=threshold,
            #     total_parties=total_parties,
            #     party_index=party_index,
            # )
            # response = await self.stub.StartDKG(request)
            
            # Simulation: Generate a placeholder message
            import secrets
            round1_msg = secrets.token_bytes(64)
            
            return True, round1_msg, None
            
        except Exception as e:
            logger.error(f"Failed to start DKG: {e}")
            return False, None, str(e)
    
    async def process_dkg_round(
        self,
        session_id: str,
        round_num: int,
        incoming_messages: List[bytes],
    ) -> Tuple[bool, Optional[bytes], Optional[DKGResult], bool, Optional[str]]:
        """
        Process a DKG round on the bank signer.
        
        Returns:
            (success, outgoing_message, result, is_final, error)
        """
        logger.debug(f"Processing DKG round {round_num} for session {session_id}")
        
        try:
            # TODO: Call actual gRPC method
            # request = mpc_pb2.DKGRoundRequest(
            #     session_id=session_id,
            #     round=round_num,
            #     incoming_messages=[
            #         mpc_pb2.PartyMessage(from_party=1, payload=msg)
            #         for msg in incoming_messages
            #     ],
            # )
            # response = await self.stub.DKGRound(request)
            
            # Simulation: DKG completes after round 3
            import secrets
            from eth_keys import keys
            
            if round_num >= 3:
                # Generate actual key for simulation
                private_key_bytes = secrets.token_bytes(32)
                pk = keys.PrivateKey(private_key_bytes)
                public_key = pk.public_key
                address = public_key.to_checksum_address()
                
                keyset_id = str(uuid4())
                
                result = DKGResult(
                    keyset_id=keyset_id,
                    public_key=public_key.to_bytes()[:33],  # Compressed
                    public_key_full=public_key.to_bytes(),
                    ethereum_address=address,
                    user_share=secrets.token_bytes(64),  # Simulated user share
                )
                
                return True, None, result, True, None
            else:
                out_msg = secrets.token_bytes(64)
                return True, out_msg, None, False, None
                
        except Exception as e:
            logger.error(f"DKG round failed: {e}")
            return False, None, None, False, str(e)
    
    # =========================================================================
    # Signing Operations
    # =========================================================================
    
    async def start_signing(
        self,
        session_id: str,
        keyset_id: str,
        message_hash: bytes,
        permit: SigningPermit,
        party_index: int = 0,
    ) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Start a signing session on the bank signer.
        
        Returns:
            (success, round1_message, error)
        """
        logger.info(f"Starting signing session {session_id} on bank signer")
        
        try:
            # TODO: Call actual gRPC method
            # request = mpc_pb2.StartSigningRequest(
            #     session_id=session_id,
            #     keyset_id=keyset_id,
            #     message_hash=message_hash,
            #     permit=mpc_pb2.SigningPermit(
            #         tx_request_id=permit.tx_request_id,
            #         wallet_id=permit.wallet_id,
            #         keyset_id=permit.keyset_id,
            #         tx_hash=permit.tx_hash,
            #         expires_at=permit.expires_at,
            #         coordinator_signature=permit.coordinator_signature,
            #     ),
            #     party_index=party_index,
            # )
            # response = await self.stub.StartSigning(request)
            
            import secrets
            round1_msg = secrets.token_bytes(64)
            
            return True, round1_msg, None
            
        except Exception as e:
            logger.error(f"Failed to start signing: {e}")
            return False, None, str(e)
    
    async def process_signing_round(
        self,
        session_id: str,
        round_num: int,
        incoming_messages: List[bytes],
    ) -> Tuple[bool, Optional[bytes], Optional[SigningResult], bool, Optional[str]]:
        """
        Process a signing round on the bank signer.
        
        Returns:
            (success, outgoing_message, result, is_final, error)
        """
        logger.debug(f"Processing signing round {round_num} for session {session_id}")
        
        try:
            # TODO: Call actual gRPC method
            
            # Simulation: Signing completes after round 8 (GG20 has ~8-9 rounds)
            import secrets
            
            if round_num >= 8:
                r = secrets.token_bytes(32)
                s = secrets.token_bytes(32)
                v = 27
                
                full_sig = r + s + bytes([v])
                
                result = SigningResult(
                    signature_r=r,
                    signature_s=s,
                    signature_v=v,
                    full_signature=full_sig,
                )
                
                return True, None, result, True, None
            else:
                out_msg = secrets.token_bytes(64)
                return True, out_msg, None, False, None
                
        except Exception as e:
            logger.error(f"Signing round failed: {e}")
            return False, None, None, False, str(e)
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    @staticmethod
    def create_permit(
        tx_request_id: str,
        wallet_id: str,
        keyset_id: str,
        tx_hash: bytes,
        ttl_seconds: int = 300,
    ) -> SigningPermit:
        """
        Create a signed permit for signing authorization.
        
        The permit proves that the Core API has authorized this signing operation.
        The bank signer will verify this before participating.
        """
        expires_at = int(time.time()) + ttl_seconds
        
        # Compute HMAC signature
        h = hmac.new(PERMIT_SECRET, digestmod=hashlib.sha256)
        h.update(tx_request_id.encode())
        h.update(wallet_id.encode())
        h.update(keyset_id.encode())
        h.update(tx_hash)
        h.update(str(expires_at).encode())
        signature = h.digest()
        
        return SigningPermit(
            tx_request_id=tx_request_id,
            wallet_id=wallet_id,
            keyset_id=keyset_id,
            tx_hash=tx_hash,
            expires_at=expires_at,
            coordinator_signature=signature,
        )
    
    @staticmethod
    def verify_permit(permit: SigningPermit) -> bool:
        """Verify a signing permit's signature."""
        if time.time() > permit.expires_at:
            return False
        
        h = hmac.new(PERMIT_SECRET, digestmod=hashlib.sha256)
        h.update(permit.tx_request_id.encode())
        h.update(permit.wallet_id.encode())
        h.update(permit.keyset_id.encode())
        h.update(permit.tx_hash)
        h.update(str(permit.expires_at).encode())
        expected = h.digest()
        
        return hmac.compare_digest(permit.coordinator_signature, expected)


# Global client instance
_client: Optional[MPCSignerClient] = None


def get_mpc_signer_client() -> MPCSignerClient:
    """Get or create the global MPC signer client."""
    global _client
    if _client is None:
        settings = get_settings()
        signer_url = getattr(settings, 'mpc_signer_url', 'localhost:50051')
        _client = MPCSignerClient(signer_url)
    return _client


async def initialize_mpc_signer_client():
    """Initialize and connect the MPC signer client."""
    client = get_mpc_signer_client()
    await client.connect()


async def shutdown_mpc_signer_client():
    """Shutdown the MPC signer client."""
    global _client
    if _client:
        await _client.disconnect()
        _client = None

