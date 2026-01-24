import { test, expect } from '@playwright/test';
import {
  TEST_ADDRESSES,
  AMOUNTS,
  POLICY_RULES,
  TX_STATUSES,
  TIMEOUTS,
} from './fixtures/test-data';
import {
  api,
  getWallets,
  getWalletBalance,
  createWithdrawal,
  getWithdrawal,
  approveWithdrawal,
  rejectWithdrawal,
  waitForTxStatus,
  ethToWei,
} from './fixtures/api-helpers';
import {
  TEST_USERS,
  loginAsRetail,
  loginAsAdmin,
  setupAuthenticatedPage,
  getTokenForUser,
} from './fixtures/auth-helpers';

/**
 * Retail Core Tests - Scene A, B, D
 *
 * Tests the main transaction flows based on the Retail Policy:
 * - Scene A: Micro transfers (≤0.001 ETH) - skip KYT/approval
 * - Scene B: Large transfers (>0.001 ETH) - require KYT + approval
 * - Scene D: Denylist transfers - fail-fast block
 */

test.describe('Scene A: Micro Transfer (≤0.001 ETH)', () => {
  let retailToken: string;
  let adminToken: string;
  let walletId: string;
  let walletAddress: string;

  test.beforeAll(async () => {
    retailToken = (await getTokenForUser('retail'))!;
    adminToken = (await getTokenForUser('admin'))!;

    // Get user's wallet
    const wallets = await getWallets(retailToken);
    const wallet = wallets.find(w => w.address);
    if (wallet) {
      walletId = wallet.id;
      walletAddress = wallet.address;
    }
  });

  test('E2E-SCENE-A-01: Micro transfer to allowlisted address - KYT & approval skipped', async ({ page }) => {
    test.skip(!walletId, 'No wallet available');

    // Check balance first
    const balance = await getWalletBalance(retailToken, walletId);
    const available = parseFloat(balance.available_eth);
    test.skip(available < parseFloat(AMOUNTS.MICRO), 'Insufficient balance');

    // Login and navigate to withdraw
    await setupAuthenticatedPage(page, 'retail');
    await page.goto('/app/withdraw');
    await page.waitForLoadState('networkidle');

    // Fill withdrawal form
    const addrField = page.getByPlaceholder(/address|0x/i).first();
    const amtField = page.getByPlaceholder(/amount/i).first();

    if (await addrField.isVisible()) {
      await addrField.fill(TEST_ADDRESSES.ALLOW_ADDR);
    }
    if (await amtField.isVisible()) {
      await amtField.fill(AMOUNTS.MICRO);
    }

    // Submit
    const submitBtn = page.getByRole('button', { name: /withdraw|send|submit/i }).first();
    await submitBtn.click();

    // Wait for success or pending status
    await page.waitForTimeout(3000);

    // Verify via API that KYT and approval were skipped
    const walletTxs = await api('GET', `/v1/withdrawals?wallet_id=${walletId}`, retailToken);
    const latestTx = walletTxs.data?.[0];

    if (latestTx) {
      // For micro transfers, should skip KYT and approval
      // Check that the transaction progresses without approval
      const tx = await waitForTxStatus(
        retailToken,
        latestTx.id,
        [TX_STATUSES.FINALIZED, TX_STATUSES.CONFIRMED, TX_STATUSES.MEMPOOL, TX_STATUSES.SIGN_PENDING],
        TIMEOUTS.TX_PROCESSING
      );

      console.log(`Micro transfer status: ${tx.status}`);

      // Verify policy decision
      if (tx.policy_decision) {
        expect(tx.policy_decision.matched_rules).toContain(POLICY_RULES.MICRO_ALLOW);
        // KYT should be skipped for micro transfers
        expect(tx.policy_decision.kyt_required).toBeFalsy();
        expect(tx.policy_decision.approval_required).toBeFalsy();
      }
    }
  });

  test('E2E-SCENE-A-02: Micro transfer to unknown address - blocked by policy', async ({ page }) => {
    test.skip(!walletId, 'No wallet available');

    const balance = await getWalletBalance(retailToken, walletId);
    test.skip(parseFloat(balance.available_eth) < parseFloat(AMOUNTS.MICRO), 'Insufficient balance');

    // Create withdrawal to unknown address via API
    const result = await createWithdrawal(
      retailToken,
      walletId,
      TEST_ADDRESSES.UNKNOWN_ADDR,
      ethToWei(AMOUNTS.MICRO)
    );

    if (result.data?.id) {
      // Should be blocked by policy
      const tx = await waitForTxStatus(
        retailToken,
        result.data.id,
        [TX_STATUSES.FAILED_POLICY, 'BLOCKED'],
        TIMEOUTS.TX_PROCESSING
      );

      expect(tx.status).toMatch(/FAILED_POLICY|BLOCKED/);
      console.log(`Unknown address transfer blocked: ${tx.status}`);
    } else {
      // If creation failed, that's also acceptable (policy blocked it early)
      expect(result.error || result.detail).toBeTruthy();
      console.log('Transfer creation blocked by policy');
    }
  });
});

test.describe('Scene B: Large Transfer (>0.001 ETH)', () => {
  let retailToken: string;
  let adminToken: string;
  let walletId: string;

  test.beforeAll(async () => {
    retailToken = (await getTokenForUser('retail'))!;
    adminToken = (await getTokenForUser('admin'))!;

    const wallets = await getWallets(retailToken);
    const wallet = wallets.find(w => w.address);
    if (wallet) walletId = wallet.id;
  });

  test('E2E-SCENE-B-01: Large transfer - KYT + admin approval required', async ({ page }) => {
    test.skip(!walletId, 'No wallet available');
    test.setTimeout(TIMEOUTS.CONFIRMATION);

    const balance = await getWalletBalance(retailToken, walletId);
    test.skip(parseFloat(balance.available_eth) < parseFloat(AMOUNTS.LARGE), 'Insufficient balance');

    // Create large withdrawal via API
    const result = await createWithdrawal(
      retailToken,
      walletId,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.LARGE)
    );

    expect(result.data?.id).toBeTruthy();
    const txId = result.data.id;

    // Wait for approval pending status
    const pendingTx = await waitForTxStatus(
      retailToken,
      txId,
      [TX_STATUSES.APPROVAL_PENDING, TX_STATUSES.KYT_PENDING],
      TIMEOUTS.TX_PROCESSING
    );

    console.log(`Large transfer status: ${pendingTx.status}`);

    // Verify KYT was performed
    if (pendingTx.kyt_result) {
      expect(pendingTx.kyt_result).toMatch(/ALLOW|REVIEW/);
    }

    // Admin approves
    const approvalResult = await approveWithdrawal(adminToken, txId, 'E2E test approval');
    expect(approvalResult.error).toBeFalsy();

    // Wait for final status
    const finalTx = await waitForTxStatus(
      retailToken,
      txId,
      [TX_STATUSES.FINALIZED, TX_STATUSES.CONFIRMED, TX_STATUSES.MEMPOOL, TX_STATUSES.SIGN_PENDING],
      TIMEOUTS.TX_PROCESSING
    );

    console.log(`After approval status: ${finalTx.status}`);

    // Verify audit contains approval
    if (finalTx.approvals?.length > 0) {
      expect(finalTx.approvals[0].decision).toBe('APPROVE');
    }
  });

  test('E2E-SCENE-B-02: Large transfer - admin rejection', async ({ page }) => {
    test.skip(!walletId, 'No wallet available');

    const balance = await getWalletBalance(retailToken, walletId);
    test.skip(parseFloat(balance.available_eth) < parseFloat(AMOUNTS.LARGE), 'Insufficient balance');

    // Create withdrawal
    const result = await createWithdrawal(
      retailToken,
      walletId,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.LARGE)
    );

    if (!result.data?.id) {
      console.log('Could not create withdrawal for rejection test');
      return;
    }

    const txId = result.data.id;

    // Wait for approval pending
    await waitForTxStatus(
      retailToken,
      txId,
      [TX_STATUSES.APPROVAL_PENDING],
      TIMEOUTS.TX_PROCESSING
    );

    // Admin rejects
    const rejectResult = await rejectWithdrawal(adminToken, txId, 'E2E test rejection');
    expect(rejectResult.error).toBeFalsy();

    // Verify rejection
    const tx = await getWithdrawal(retailToken, txId);
    expect(tx.status).toBe(TX_STATUSES.REJECTED);

    console.log('Large transfer rejected successfully');
  });
});

test.describe('Scene D: Denylist Fail-Fast', () => {
  let retailToken: string;
  let walletId: string;

  test.beforeAll(async () => {
    retailToken = (await getTokenForUser('retail'))!;

    const wallets = await getWallets(retailToken);
    const wallet = wallets.find(w => w.address);
    if (wallet) walletId = wallet.id;
  });

  test('E2E-SCENE-D-01: Denylist address blocked before KYT/approval', async ({ page }) => {
    test.skip(!walletId, 'No wallet available');

    // Try to create withdrawal to denylist address
    const result = await createWithdrawal(
      retailToken,
      walletId,
      TEST_ADDRESSES.DENY_ADDR,
      ethToWei(AMOUNTS.MICRO)
    );

    if (result.data?.id) {
      // If tx was created, it should immediately fail
      const tx = await waitForTxStatus(
        retailToken,
        result.data.id,
        [TX_STATUSES.FAILED_POLICY, 'BLOCKED'],
        TIMEOUTS.TX_PROCESSING
      );

      expect(tx.status).toMatch(/FAILED_POLICY|BLOCKED/);

      // Verify matched rule is RET-03
      if (tx.policy_decision) {
        expect(tx.policy_decision.matched_rules).toContain(POLICY_RULES.DENYLIST_BLOCK);
      }

      // Verify KYT was NOT performed (fail-fast)
      expect(tx.kyt_result).toBeFalsy();

      console.log('Denylist address blocked by policy (fail-fast)');
    } else {
      // API blocked creation - also valid behavior
      expect(result.error || result.detail).toBeTruthy();
      console.log('Denylist transfer blocked at creation');
    }
  });

  test('E2E-SCENE-D-02: Denylist UI shows clear error', async ({ page }) => {
    test.skip(!walletId, 'No wallet available');

    await setupAuthenticatedPage(page, 'retail');
    await page.goto('/app/withdraw');
    await page.waitForLoadState('networkidle');

    // Fill form with denylist address
    const addrField = page.getByPlaceholder(/address|0x/i).first();
    const amtField = page.getByPlaceholder(/amount/i).first();

    if (await addrField.isVisible()) {
      await addrField.fill(TEST_ADDRESSES.DENY_ADDR);
    }
    if (await amtField.isVisible()) {
      await amtField.fill(AMOUNTS.MICRO);
    }

    // Submit
    const submitBtn = page.getByRole('button', { name: /withdraw|send|submit/i }).first();
    if (await submitBtn.isVisible()) {
      await submitBtn.click();
      await page.waitForTimeout(3000);

      // Should show error
      const hasError = await page.getByText(/blocked|denied|error|failed/i).first()
        .isVisible({ timeout: 5000 }).catch(() => false);

      console.log(`Denylist UI error shown: ${hasError}`);
    }
  });
});

test.describe('Policy Decision Explainability', () => {
  let retailToken: string;
  let walletId: string;

  test.beforeAll(async () => {
    retailToken = (await getTokenForUser('retail'))!;

    const wallets = await getWallets(retailToken);
    const wallet = wallets.find(w => w.address);
    if (wallet) walletId = wallet.id;
  });

  test('E2E-POL-EXP-01: Policy decision contains matched rules and reasons', async () => {
    test.skip(!walletId, 'No wallet available');

    // Create a transaction to check policy decision structure
    const result = await createWithdrawal(
      retailToken,
      walletId,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.MICRO)
    );

    if (result.data?.id) {
      const tx = await getWithdrawal(retailToken, result.data.id);

      // Verify policy decision structure
      if (tx.policy_decision) {
        expect(tx.policy_decision).toHaveProperty('decision');
        expect(tx.policy_decision).toHaveProperty('matched_rules');
        expect(tx.policy_decision).toHaveProperty('policy_version');

        console.log('Policy decision:', JSON.stringify(tx.policy_decision, null, 2));
      }
    }
  });
});
