#!/bin/bash
# Collider Custody API - curl examples
# 
# This script demonstrates the full end-to-end workflow:
# 1. Register users
# 2. Create wallet
# 3. Assign roles
# 4. Create transaction request
# 5. Approve transaction (SoD)
# 6. Get audit package

BASE_URL="http://localhost:8000"

echo "=== Collider Custody API Demo ==="
echo ""

# ============================================
# 1. REGISTER USERS
# ============================================
echo "--- 1. Registering Admin User ---"
ADMIN_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-register-admin" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "securepass123",
    "role": "ADMIN"
  }')
echo "$ADMIN_RESPONSE" | jq .
ADMIN_ID=$(echo "$ADMIN_RESPONSE" | jq -r '.data.id')

echo ""
echo "--- Registering Operator User ---"
OPERATOR_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-register-operator" \
  -d '{
    "username": "operator1",
    "email": "operator1@example.com",
    "password": "securepass123",
    "role": "OPERATOR"
  }')
echo "$OPERATOR_RESPONSE" | jq .
OPERATOR_ID=$(echo "$OPERATOR_RESPONSE" | jq -r '.data.id')

echo ""
echo "--- Registering Compliance User ---"
COMPLIANCE_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-register-compliance" \
  -d '{
    "username": "compliance1",
    "email": "compliance1@example.com",
    "password": "securepass123",
    "role": "COMPLIANCE"
  }')
echo "$COMPLIANCE_RESPONSE" | jq .
COMPLIANCE_ID=$(echo "$COMPLIANCE_RESPONSE" | jq -r '.data.id')

# ============================================
# 2. LOGIN TO GET TOKENS
# ============================================
echo ""
echo "--- 2. Login as Admin ---"
ADMIN_LOGIN=$(curl -s -X POST "$BASE_URL/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "securepass123"}')
echo "$ADMIN_LOGIN" | jq .
ADMIN_TOKEN=$(echo "$ADMIN_LOGIN" | jq -r '.data.access_token')

echo ""
echo "--- Login as Operator ---"
OPERATOR_LOGIN=$(curl -s -X POST "$BASE_URL/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "operator1", "password": "securepass123"}')
OPERATOR_TOKEN=$(echo "$OPERATOR_LOGIN" | jq -r '.data.access_token')

echo ""
echo "--- Login as Compliance ---"
COMPLIANCE_LOGIN=$(curl -s -X POST "$BASE_URL/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "compliance1", "password": "securepass123"}')
COMPLIANCE_TOKEN=$(echo "$COMPLIANCE_LOGIN" | jq -r '.data.access_token')

# ============================================
# 3. CREATE WALLET
# ============================================
echo ""
echo "--- 3. Creating TREASURY Wallet ---"
WALLET_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/wallets" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: wallet-demo-001" \
  -H "X-Correlation-ID: demo-create-wallet" \
  -d '{
    "wallet_type": "TREASURY",
    "subject_id": "org-acme-corp",
    "tags": {"department": "finance", "cost_center": "CC-001"},
    "risk_profile": "HIGH"
  }')
echo "$WALLET_RESPONSE" | jq .
WALLET_ID=$(echo "$WALLET_RESPONSE" | jq -r '.data.id')
WALLET_ADDRESS=$(echo "$WALLET_RESPONSE" | jq -r '.data.address')

echo ""
echo "Wallet ID: $WALLET_ID"
echo "Wallet Address: $WALLET_ADDRESS"

# ============================================
# 4. ASSIGN ROLES TO WALLET
# ============================================
echo ""
echo "--- 4. Assigning Roles to Wallet ---"

echo "Assigning APPROVER role to operator1..."
curl -s -X POST "$BASE_URL/v1/wallets/$WALLET_ID/roles" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-assign-role-1" \
  -d "{
    \"user_id\": \"$OPERATOR_ID\",
    \"role\": \"APPROVER\"
  }" | jq .

echo ""
echo "Assigning APPROVER role to compliance1..."
curl -s -X POST "$BASE_URL/v1/wallets/$WALLET_ID/roles" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-assign-role-2" \
  -d "{
    \"user_id\": \"$COMPLIANCE_ID\",
    \"role\": \"APPROVER\"
  }" | jq .

# ============================================
# 5. CREATE POLICIES
# ============================================
echo ""
echo "--- 5. Creating Policies ---"

echo "Creating address denylist policy..."
curl -s -X POST "$BASE_URL/v1/policies" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-create-policy-1" \
  -d '{
    "name": "Blocked Address - Known Bad Actor",
    "policy_type": "ADDRESS_DENYLIST",
    "address": "0x000000000000000000000000000000000000dead"
  }' | jq .

echo ""
echo "Creating daily limit policy for TREASURY..."
curl -s -X POST "$BASE_URL/v1/policies" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-create-policy-2" \
  -d '{
    "name": "Treasury Daily Limit",
    "policy_type": "DAILY_LIMIT",
    "wallet_type": "TREASURY",
    "limit_amount": "100.0"
  }' | jq .

# ============================================
# 6. CREATE TRANSACTION REQUEST
# ============================================
echo ""
echo "--- 6. Creating Transaction Request (by Admin) ---"
TX_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tx-requests" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: tx-demo-001" \
  -H "X-Correlation-ID: demo-create-tx" \
  -d "{
    \"wallet_id\": \"$WALLET_ID\",
    \"tx_type\": \"TRANSFER\",
    \"to_address\": \"0x742d35Cc6634C0532925a3b844Bc9e7595f2bD20\",
    \"asset\": \"ETH\",
    \"amount\": \"0.1\"
  }")
echo "$TX_RESPONSE" | jq .
TX_ID=$(echo "$TX_RESPONSE" | jq -r '.data.id')
TX_STATUS=$(echo "$TX_RESPONSE" | jq -r '.data.status')

echo ""
echo "Transaction ID: $TX_ID"
echo "Transaction Status: $TX_STATUS"

# ============================================
# 7. APPROVE TRANSACTION (SoD)
# ============================================
echo ""
echo "--- 7. Approving Transaction ---"

# Note: Admin created the tx, so Admin CANNOT approve (SoD)
echo "First approval by operator1..."
APPROVAL1=$(curl -s -X POST "$BASE_URL/v1/tx-requests/$TX_ID/approve" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-approve-1" \
  -d '{"decision": "APPROVED", "comment": "Reviewed - amount within limits"}')
echo "$APPROVAL1" | jq .

echo ""
echo "Second approval by compliance1..."
APPROVAL2=$(curl -s -X POST "$BASE_URL/v1/tx-requests/$TX_ID/approve" \
  -H "Authorization: Bearer $COMPLIANCE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-approve-2" \
  -d '{"decision": "APPROVED", "comment": "Compliance check passed"}')
echo "$APPROVAL2" | jq .

# ============================================
# 8. CHECK TRANSACTION STATUS
# ============================================
echo ""
echo "--- 8. Checking Transaction Status ---"
TX_STATUS_RESPONSE=$(curl -s "$BASE_URL/v1/tx-requests/$TX_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Correlation-ID: demo-check-status")
echo "$TX_STATUS_RESPONSE" | jq .

# ============================================
# 9. GET AUDIT PACKAGE
# ============================================
echo ""
echo "--- 9. Getting Audit Package ---"
AUDIT_PACKAGE=$(curl -s "$BASE_URL/v1/audit/packages/$TX_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Correlation-ID: demo-audit-package")
echo "$AUDIT_PACKAGE" | jq .

# ============================================
# 10. VERIFY AUDIT CHAIN
# ============================================
echo ""
echo "--- 10. Verifying Audit Chain Integrity ---"
VERIFY_RESPONSE=$(curl -s "$BASE_URL/v1/audit/verify" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Correlation-ID: demo-verify-chain")
echo "$VERIFY_RESPONSE" | jq .

# ============================================
# DEMO: KYT BLOCKING
# ============================================
echo ""
echo "=== Demo: KYT Blocking ==="
echo "Creating transaction to blacklisted address..."
KYT_BLOCK_TX=$(curl -s -X POST "$BASE_URL/v1/tx-requests" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: tx-demo-blocked" \
  -H "X-Correlation-ID: demo-kyt-block" \
  -d "{
    \"wallet_id\": \"$WALLET_ID\",
    \"tx_type\": \"TRANSFER\",
    \"to_address\": \"0x000000000000000000000000000000000000dead\",
    \"asset\": \"ETH\",
    \"amount\": \"0.01\"
  }")
echo "$KYT_BLOCK_TX" | jq .
BLOCKED_TX_STATUS=$(echo "$KYT_BLOCK_TX" | jq -r '.data.status')
echo "Status: $BLOCKED_TX_STATUS (should be KYT_BLOCKED)"

# ============================================
# DEMO: KYT REVIEW (graylist)
# ============================================
echo ""
echo "=== Demo: KYT Review Workflow ==="
echo "Creating transaction to graylisted address..."
KYT_REVIEW_TX=$(curl -s -X POST "$BASE_URL/v1/tx-requests" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: tx-demo-review" \
  -H "X-Correlation-ID: demo-kyt-review" \
  -d "{
    \"wallet_id\": \"$WALLET_ID\",
    \"tx_type\": \"TRANSFER\",
    \"to_address\": \"0x1234567890123456789012345678901234567890\",
    \"asset\": \"ETH\",
    \"amount\": \"0.01\"
  }")
echo "$KYT_REVIEW_TX" | jq .
REVIEW_TX_ID=$(echo "$KYT_REVIEW_TX" | jq -r '.data.id')
KYT_CASE_ID=$(echo "$KYT_REVIEW_TX" | jq -r '.data.kyt_case_id')
echo "Status: $(echo "$KYT_REVIEW_TX" | jq -r '.data.status') (should be KYT_REVIEW)"
echo "KYT Case ID: $KYT_CASE_ID"

echo ""
echo "Listing pending KYT cases..."
curl -s "$BASE_URL/v1/cases?status=PENDING" \
  -H "Authorization: Bearer $COMPLIANCE_TOKEN" \
  -H "X-Correlation-ID: demo-list-cases" | jq .

if [ "$KYT_CASE_ID" != "null" ]; then
  echo ""
  echo "Resolving KYT case with ALLOW..."
  curl -s -X POST "$BASE_URL/v1/cases/$KYT_CASE_ID/resolve" \
    -H "Authorization: Bearer $COMPLIANCE_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: demo-resolve-case" \
    -d '{"decision": "ALLOW", "comment": "Manual review completed - legitimate address"}' | jq .
  
  echo ""
  echo "Resuming transaction after KYT resolution..."
  curl -s -X POST "$BASE_URL/v1/tx-requests/$REVIEW_TX_ID/resume" \
    -H "Authorization: Bearer $COMPLIANCE_TOKEN" \
    -H "X-Correlation-ID: demo-resume-tx" | jq .
fi

echo ""
echo "=== Demo Complete ==="
echo ""
echo "Summary:"
echo "- Admin ID: $ADMIN_ID"
echo "- Operator ID: $OPERATOR_ID"
echo "- Compliance ID: $COMPLIANCE_ID"
echo "- Wallet ID: $WALLET_ID"
echo "- Wallet Address: $WALLET_ADDRESS"
echo "- Transaction ID: $TX_ID"

# ============================================
# MPC WALLET DEMO (Optional - uncomment to run)
# ============================================
echo ""
echo "=== MPC Wallet Demo (Optional) ==="
echo ""

# Uncomment the following to test MPC wallet creation
# Note: This requires the MPC migration to be applied

MPC_DEMO_ENABLED=${MPC_DEMO_ENABLED:-false}

if [ "$MPC_DEMO_ENABLED" = "true" ]; then
  echo "--- Creating MPC Wallet (2-of-3 threshold) ---"
  MPC_WALLET_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/wallets/mpc" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: demo-create-mpc-wallet" \
    -H "Idempotency-Key: mpc-wallet-001" \
    -d '{
      "wallet_type": "TREASURY",
      "subject_id": "mpc-org-123",
      "tags": {"type": "mpc_demo", "purpose": "threshold_signing"},
      "risk_profile": "HIGH",
      "mpc_threshold_t": 2,
      "mpc_total_n": 3
    }')
  echo "$MPC_WALLET_RESPONSE" | jq .
  
  MPC_WALLET_ID=$(echo "$MPC_WALLET_RESPONSE" | jq -r '.data.id')
  MPC_WALLET_ADDRESS=$(echo "$MPC_WALLET_RESPONSE" | jq -r '.data.address')
  MPC_KEYSET_ID=$(echo "$MPC_WALLET_RESPONSE" | jq -r '.data.mpc_keyset_id')
  MPC_CUSTODY=$(echo "$MPC_WALLET_RESPONSE" | jq -r '.data.custody_backend')
  
  echo ""
  echo "MPC Wallet Created:"
  echo "- ID: $MPC_WALLET_ID"
  echo "- Address: $MPC_WALLET_ADDRESS"
  echo "- Keyset ID: $MPC_KEYSET_ID"
  echo "- Custody Backend: $MPC_CUSTODY"
  
  echo ""
  echo "--- Getting MPC Keyset Info ---"
  curl -s -X GET "$BASE_URL/v1/wallets/$MPC_WALLET_ID/mpc" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "X-Correlation-ID: demo-get-mpc-info" | jq .
  
  echo ""
  echo "--- Assigning Approvers to MPC Wallet ---"
  
  # Assign operator as approver
  curl -s -X POST "$BASE_URL/v1/wallets/$MPC_WALLET_ID/roles" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: demo-mpc-assign-role-1" \
    -d "{\"user_id\": \"$OPERATOR_ID\", \"role\": \"APPROVER\"}" | jq .
  
  # Assign compliance as approver
  curl -s -X POST "$BASE_URL/v1/wallets/$MPC_WALLET_ID/roles" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: demo-mpc-assign-role-2" \
    -d "{\"user_id\": \"$COMPLIANCE_ID\", \"role\": \"APPROVER\"}" | jq .
  
  echo ""
  echo "--- Creating TX Request with MPC Wallet ---"
  MPC_TX_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/tx-requests" \
    -H "Authorization: Bearer $OPERATOR_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: demo-mpc-tx" \
    -H "Idempotency-Key: mpc-tx-001" \
    -d "{
      \"wallet_id\": \"$MPC_WALLET_ID\",
      \"tx_type\": \"TRANSFER\",
      \"to_address\": \"0x742d35Cc6634C0532925a3b844Bc9e7595f3c111\",
      \"asset\": \"ETH\",
      \"amount\": \"0.001\"
    }")
  echo "$MPC_TX_RESPONSE" | jq .
  
  MPC_TX_ID=$(echo "$MPC_TX_RESPONSE" | jq -r '.data.id')
  MPC_TX_STATUS=$(echo "$MPC_TX_RESPONSE" | jq -r '.data.status')
  
  echo ""
  echo "MPC TX Created:"
  echo "- TX ID: $MPC_TX_ID"
  echo "- Status: $MPC_TX_STATUS"
  
  # If tx requires approvals, approve with 2 users (TREASURY requires 2-of-3)
  if [ "$MPC_TX_STATUS" = "APPROVAL_PENDING" ]; then
    echo ""
    echo "--- Approving MPC TX (First approval - Admin) ---"
    curl -s -X POST "$BASE_URL/v1/tx-requests/$MPC_TX_ID/approve" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -H "X-Correlation-ID: demo-mpc-approve-1" \
      -d '{"decision": "APPROVED", "comment": "MPC TX approved by admin"}' | jq .
    
    echo ""
    echo "--- Approving MPC TX (Second approval - Compliance) ---"
    # This should trigger MPC signing with SigningPermit
    curl -s -X POST "$BASE_URL/v1/tx-requests/$MPC_TX_ID/approve" \
      -H "Authorization: Bearer $COMPLIANCE_TOKEN" \
      -H "Content-Type: application/json" \
      -H "X-Correlation-ID: demo-mpc-approve-2" \
      -d '{"decision": "APPROVED", "comment": "MPC TX approved by compliance"}' | jq .
    
    echo ""
    echo "--- Checking MPC TX Final Status ---"
    curl -s -X GET "$BASE_URL/v1/tx-requests/$MPC_TX_ID" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "X-Correlation-ID: demo-mpc-status" | jq .
  fi
  
  echo ""
  echo "=== MPC Demo Complete ==="
  echo ""
  echo "MPC Summary:"
  echo "- MPC Wallet ID: $MPC_WALLET_ID"
  echo "- MPC Address: $MPC_WALLET_ADDRESS (derived from MPC pubkey)"
  echo "- Threshold: 2-of-3"
  echo "- MPC TX ID: $MPC_TX_ID"
else
  echo "MPC Demo skipped. Set MPC_DEMO_ENABLED=true to run."
  echo ""
  echo "Example: MPC_DEMO_ENABLED=true bash examples/curl_examples.sh"
fi

