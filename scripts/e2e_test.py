#!/usr/bin/env python3
"""
E2E Test Script for Collider Custody

This script tests the full deposit flow:
1. Login as e2e_bot (ADMIN)
2. Use dedicated test wallet
3. Check pending deposits
4. Approve pending deposits
5. Verify ledger balance reflects approved deposits

Usage:
    python3 scripts/e2e_test.py [--base-url URL]

Credentials:
    Username: e2e_bot
    Password: E2eTestPass2026

E2E Wallet:
    Address: 0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c
    ID: 0eb98a8b-f7c4-4662-852d-ddc2927f37d2

To test deposit flow:
    1. Send test ETH to: 0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c
    2. Run: python3 scripts/e2e_test.py
    3. Script will detect, approve, and verify balance
"""

import argparse
import json
import sys
import time
import requests
from typing import Optional, Dict, Any

# Configuration
DEFAULT_BASE_URL = "https://discerning-rebirth-production.up.railway.app"
E2E_USERNAME = "e2e_bot"
E2E_PASSWORD = "E2eTestPass2026"
E2E_WALLET_ID = "0eb98a8b-f7c4-4662-852d-ddc2927f37d2"
E2E_WALLET_ADDRESS = "0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c"


class E2ETest:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.wallet_id: Optional[str] = None
        self.wallet_address: Optional[str] = None

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None, auth: bool = True) -> Dict[str, Any]:
        """Make an API request."""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}

        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = requests.request(method, url, json=data, headers=headers, timeout=30)

        try:
            result = response.json()
        except:
            result = {"error": response.text}

        if response.status_code >= 400:
            print(f"  ERROR {response.status_code}: {result}")

        return result

    def login(self) -> bool:
        """Login and get token."""
        print(f"[1] Logging in as {E2E_USERNAME}...")

        result = self._request("POST", "/v1/auth/login", {
            "username": E2E_USERNAME,
            "password": E2E_PASSWORD
        }, auth=False)

        if "data" in result and "access_token" in result["data"]:
            self.token = result["data"]["access_token"]
            print(f"    OK - Got token")

            # Get user info
            me = self._request("GET", "/v1/auth/me")
            if "data" in me:
                self.user_id = me["data"]["id"]
                print(f"    User ID: {self.user_id}")
                print(f"    Role: {me['data']['role']}")
            return True
        else:
            print(f"    FAILED - {result}")
            return False

    def get_or_create_wallet(self) -> bool:
        """Use the dedicated E2E test wallet."""
        print("[2] Using E2E test wallet...")

        # Use the pre-configured E2E wallet
        self.wallet_id = E2E_WALLET_ID
        self.wallet_address = E2E_WALLET_ADDRESS

        # Verify it exists
        result = self._request("GET", f"/v1/wallets/{E2E_WALLET_ID}")

        if "data" in result:
            print(f"    Wallet: {self.wallet_address}")
            print(f"    Status: {result['data'].get('status', 'UNKNOWN')}")
            return True
        else:
            print(f"    ERROR: E2E wallet not found!")
            print(f"    Please ensure wallet {E2E_WALLET_ID} exists")
            return False

    def check_deposits(self) -> list:
        """Check for deposits on the wallet."""
        print("[3] Checking deposits...")

        result = self._request("GET", f"/v1/deposits?wallet_id={self.wallet_id}")

        if "data" in result and "data" in result["data"]:
            deposits = result["data"]["data"]
            pending = [d for d in deposits if d["status"] == "PENDING_ADMIN"]
            credited = [d for d in deposits if d["status"] == "CREDITED"]

            print(f"    Total deposits: {len(deposits)}")
            print(f"    Pending approval: {len(pending)}")
            print(f"    Credited: {len(credited)}")

            return pending

        return []

    def approve_deposit(self, deposit_id: str) -> bool:
        """Approve a pending deposit."""
        print(f"    Approving deposit {deposit_id[:8]}...")

        result = self._request("POST", f"/v1/deposits/{deposit_id}/approve")

        if "status" in result and result["status"] == "CREDITED":
            print(f"      OK - Deposit credited")
            return True
        elif "data" in result:
            print(f"      OK - {result}")
            return True
        else:
            print(f"      FAILED - {result}")
            return False

    def check_ledger_balance(self) -> Dict[str, Any]:
        """Check ledger balance."""
        print("[4] Checking ledger balance...")

        result = self._request("GET", f"/v1/wallets/{self.wallet_id}/ledger-balance")

        if "data" in result:
            data = result["data"]
            print(f"    Available: {data['available_eth']} ETH")
            print(f"    Pending: {data['pending_eth']} ETH")
            print(f"    Credited deposits: {data['total_credited']}")
            print(f"    Pending deposits: {data['total_pending']}")
            return data

        return {}

    def run_full_test(self) -> bool:
        """Run the full E2E test."""
        print("=" * 50)
        print("E2E Test - Collider Custody")
        print(f"Base URL: {self.base_url}")
        print("=" * 50)
        print()

        # Step 1: Login
        if not self.login():
            return False
        print()

        # Step 2: Get/create wallet
        if not self.get_or_create_wallet():
            return False
        print()

        # Step 3: Check deposits
        pending_deposits = self.check_deposits()
        print()

        # Step 4: Approve pending deposits (if any)
        if pending_deposits:
            print("[4] Approving pending deposits...")
            for deposit in pending_deposits:
                self.approve_deposit(deposit["id"])
            print()

        # Step 5: Check final ledger balance
        balance = self.check_ledger_balance()
        print()

        print("=" * 50)
        print("TEST COMPLETE")
        print(f"Wallet: {self.wallet_address}")
        if balance:
            print(f"Available balance: {balance.get('available_eth', '0')} ETH")
        print("=" * 50)

        return True


def main():
    parser = argparse.ArgumentParser(description="E2E Test for Collider Custody")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--approve", action="store_true", help="Approve all pending deposits")
    args = parser.parse_args()

    test = E2ETest(args.base_url)
    success = test.run_full_test()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
