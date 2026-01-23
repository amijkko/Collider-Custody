"""
gRPC client for communicating with MPC Signer Node (Bank Node).

This module handles the communication between the MPC Coordinator
and the Bank Signer Node for DKG and signing operations.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple
from uuid import uuid4

import grpc
from grpc import aio

from app.proto import mpc_pb2, mpc_pb2_grpc
from app.config import get_settings

logger = logging.getLogger(__name__)

# Get permit secret from environment
PERMIT_SECRET = os.getenv(
    "MPC_PERMIT_SECRET",
    "dev_permit_secret_minimum_32_characters_long"
).encode()


@dataclass
class DKGResult:
    """Result of a successful DKG operation."""
    keyset_id: str
    public_key: bytes
    public_key_full: bytes
    ethereum_address: str
    bank_share_saved: bool = True  # Bank signer stores its own share


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
    Client for communicating with the Bank Signer Node via gRPC.
    """

    def __init__(self, signer_url: str = "localhost:50051"):
        self.signer_url = signer_url
        self.settings = get_settings()
        self._channel: Optional[aio.Channel] = None
        self._stub: Optional[mpc_pb2_grpc.MPCSignerStub] = None
        self._connected = False

    async def connect(self) -> bool:
        """Establish gRPC connection to the signer node."""
        try:
            self._channel = aio.insecure_channel(self.signer_url)
            self._stub = mpc_pb2_grpc.MPCSignerStub(self._channel)

            # Test connection with health check
            response = await self._stub.Health(mpc_pb2.HealthRequest())
            self._connected = response.healthy

            logger.info(
                f"Connected to MPC signer at {self.signer_url}, "
                f"version={response.version}, keysets={response.stored_keysets}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MPC signer: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from the signer node."""
        if self._channel:
            await self._channel.close()
        self._connected = False
        self._stub = None
        self._channel = None

    async def health_check(self) -> dict:
        """Check signer node health."""
        if not self._stub:
            return {"healthy": False, "error": "Not connected"}

        try:
            response = await self._stub.Health(mpc_pb2.HealthRequest())
            return {
                "healthy": response.healthy,
                "version": response.version,
                "active_sessions": response.active_sessions,
                "stored_keysets": response.stored_keysets,
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"healthy": False, "error": str(e)}

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

        if not self._stub:
            return False, None, "Not connected to signer"

        try:
            request = mpc_pb2.StartDKGRequest(
                session_id=session_id,
                wallet_id=wallet_id,
                threshold=threshold,
                total_parties=total_parties,
                party_index=party_index,
            )

            response = await self._stub.StartDKG(request)

            if not response.success:
                return False, None, response.error

            return True, response.round1_msg, None

        except grpc.RpcError as e:
            logger.error(f"gRPC error starting DKG: {e.code()} - {e.details()}")
            return False, None, f"gRPC error: {e.details()}"
        except Exception as e:
            logger.error(f"Failed to start DKG: {e}")
            return False, None, str(e)

    async def process_dkg_round(
        self,
        session_id: str,
        round_num: int,
        incoming_messages: List[Tuple[int, bytes]],  # List of (from_party, payload)
    ) -> Tuple[bool, Optional[bytes], Optional[DKGResult], bool, Optional[str]]:
        """
        Process a DKG round on the bank signer.

        Args:
            session_id: Session identifier
            round_num: Current round number
            incoming_messages: List of (from_party_index, payload) tuples

        Returns:
            (success, outgoing_message, result, is_final, error)
        """
        logger.debug(f"Processing DKG round {round_num} for session {session_id}")

        if not self._stub:
            return False, None, None, False, "Not connected to signer"

        try:
            # Convert incoming messages to proto format
            party_messages = [
                mpc_pb2.PartyMessage(from_party=from_party, payload=payload)
                for from_party, payload in incoming_messages
            ]

            request = mpc_pb2.DKGRoundRequest(
                session_id=session_id,
                round=round_num,
                incoming_messages=party_messages,
            )

            response = await self._stub.DKGRound(request)

            if not response.success:
                return False, None, None, False, response.error

            result = None
            if response.is_final and response.result:
                result = DKGResult(
                    keyset_id=response.result.keyset_id,
                    public_key=response.result.public_key,
                    public_key_full=response.result.public_key_full,
                    ethereum_address=response.result.ethereum_address,
                )

            return True, response.outgoing_msg, result, response.is_final, None

        except grpc.RpcError as e:
            logger.error(f"gRPC error in DKG round: {e.code()} - {e.details()}")
            return False, None, None, False, f"gRPC error: {e.details()}"
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

        if not self._stub:
            return False, None, "Not connected to signer"

        try:
            request = mpc_pb2.StartSigningRequest(
                session_id=session_id,
                keyset_id=keyset_id,
                message_hash=message_hash,
                permit=mpc_pb2.SigningPermit(
                    tx_request_id=permit.tx_request_id,
                    wallet_id=permit.wallet_id,
                    keyset_id=permit.keyset_id,
                    tx_hash=permit.tx_hash,
                    expires_at=permit.expires_at,
                    coordinator_signature=permit.coordinator_signature,
                ),
                party_index=party_index,
            )

            response = await self._stub.StartSigning(request)

            if not response.success:
                return False, None, response.error

            return True, response.round1_msg, None

        except grpc.RpcError as e:
            logger.error(f"gRPC error starting signing: {e.code()} - {e.details()}")
            return False, None, f"gRPC error: {e.details()}"
        except Exception as e:
            logger.error(f"Failed to start signing: {e}")
            return False, None, str(e)

    async def process_signing_round(
        self,
        session_id: str,
        round_num: int,
        incoming_messages: List[Tuple[int, bytes]],  # List of (from_party, payload)
    ) -> Tuple[bool, Optional[bytes], Optional[SigningResult], bool, Optional[str]]:
        """
        Process a signing round on the bank signer.

        Returns:
            (success, outgoing_message, result, is_final, error)
        """
        logger.debug(f"Processing signing round {round_num} for session {session_id}")

        if not self._stub:
            return False, None, None, False, "Not connected to signer"

        try:
            party_messages = [
                mpc_pb2.PartyMessage(from_party=from_party, payload=payload)
                for from_party, payload in incoming_messages
            ]

            request = mpc_pb2.SigningRoundRequest(
                session_id=session_id,
                round=round_num,
                incoming_messages=party_messages,
            )

            response = await self._stub.SigningRound(request)

            if not response.success:
                return False, None, None, False, response.error

            result = None
            if response.is_final and response.result:
                result = SigningResult(
                    signature_r=response.result.signature_r,
                    signature_s=response.result.signature_s,
                    signature_v=response.result.signature_v,
                    full_signature=response.result.full_signature,
                )

            return True, response.outgoing_msg, result, response.is_final, None

        except grpc.RpcError as e:
            logger.error(f"gRPC error in signing round: {e.code()} - {e.details()}")
            return False, None, None, False, f"gRPC error: {e.details()}"
        except Exception as e:
            logger.error(f"Signing round failed: {e}")
            return False, None, None, False, str(e)

    async def get_keyset_info(self, keyset_id: str) -> Optional[dict]:
        """Get information about a stored keyset."""
        if not self._stub:
            return None

        try:
            request = mpc_pb2.GetKeysetInfoRequest(keyset_id=keyset_id)
            response = await self._stub.GetKeysetInfo(request)

            if not response.exists:
                return None

            return {
                "keyset_id": response.keyset_id,
                "wallet_id": response.wallet_id,
                "public_key": response.public_key.hex(),
                "ethereum_address": response.ethereum_address,
                "created_at": response.created_at,
                "last_used_at": response.last_used_at,
            }
        except Exception as e:
            logger.error(f"Failed to get keyset info: {e}")
            return None

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

        # Compute HMAC signature (must match MPC Signer's computePermitSignature)
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
    connected = await client.connect()
    if not connected:
        logger.warning("Failed to connect to MPC signer - some features may not work")


async def shutdown_mpc_signer_client():
    """Shutdown the MPC signer client."""
    global _client
    if _client:
        await _client.disconnect()
        _client = None
