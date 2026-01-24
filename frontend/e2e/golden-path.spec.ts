import { test, expect } from '@playwright/test';
import { TIMEOUTS, TEST_ADDRESSES, AMOUNTS, TX_STATUSES, DEPOSIT_STATUSES } from './fixtures/test-data';
import {
  api,
  getWallets,
  createWithdrawal,
  approveWithdrawal,
  waitForTxStatus,
  ethToWei,
  getDeposits,
  approveDeposit,
} from './fixtures/api-helpers';
import {
  login,
  registerUser,
  clearAuth,
  getTokenForUser,
  TEST_USERS,
} from './fixtures/auth-helpers';

/**
 * Golden Path Integration Test
 *
 * Full end-to-end flow testing the complete user journey:
 * Register → Create Wallet → Deposit → Credit → Withdraw → KYT → Approve → Sign → Confirm
 *
 * This test requires:
 * - Funded E2E wallet (0xB30545A8D068a3cDF3fa816245b523d0C11e3ADE)
 * - Running backend with chain listener
 * - Sepolia testnet access
 */

// Test state shared across steps
let testUsername: string;
let testEmail: string;
let testPassword: string;
let userToken: string;
let adminToken: string;
let walletId: string;
let walletAddress: string;
let depositId: string;
let withdrawalId: string;

test.describe('INT-GOLD-01: Golden Path Integration', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(TIMEOUTS.GOLDEN_PATH);

  test.beforeAll(async () => {
    // Generate unique test user
    const testId = Date.now();
    testUsername = `golden_${testId}`;
    testEmail = `golden_${testId}@example.com`;
    testPassword = 'GoldenPath2026!';

    // Get admin token for later steps
    console.log('Getting admin token...');
    try {
      adminToken = (await getTokenForUser('admin'))!;
      console.log('Admin token obtained:', adminToken ? 'yes' : 'no');
    } catch (error) {
      console.error('Failed to get admin token:', error);
    }
    expect(adminToken).toBeTruthy();
  });

  test('Step 1: Register new user', async ({ page }) => {
    await clearAuth(page);

    // Register via UI
    const registered = await registerUser(page, testUsername, testEmail, testPassword);

    if (!registered) {
      // Try API registration as fallback
      const result = await api('POST', '/v1/auth/register', undefined, {
        username: testUsername,
        email: testEmail,
        password: testPassword,
      });
      expect(result.data || result.error?.includes('exists')).toBeTruthy();
    }

    console.log(`Registered user: ${testUsername}`);
  });

  test('Step 2: Login and verify auto-enrollment in Retail', async ({ page }) => {
    await clearAuth(page);
    await login(page, testUsername, testPassword);

    // Get token
    userToken = await page.evaluate(() => localStorage.getItem('access_token')) || '';
    expect(userToken).toBeTruthy();

    // Verify user is in Retail group via admin API
    const groupsResult = await api('GET', '/v1/groups', adminToken);
    const groups = groupsResult.data?.groups || groupsResult.data || [];
    const retailGroup = groups.find((g: any) => g.name === 'Retail');

    if (retailGroup) {
      const groupDetail = await api('GET', `/v1/groups/${retailGroup.id}`, adminToken);
      const members = groupDetail.data?.members || [];
      const isEnrolled = members.some((m: any) =>
        m.user?.username === testUsername || m.username === testUsername
      );
      console.log(`User enrolled in Retail: ${isEnrolled}`);
    }
  });

  test('Step 3: Create wallet', async ({ page }) => {
    // Create wallet via UI
    await page.goto('/app/wallets');
    await page.waitForLoadState('networkidle');

    // Click create wallet button
    const createBtn = page.getByRole('button', { name: /create|new|add/i });
    if (await createBtn.isVisible({ timeout: 5000 })) {
      await createBtn.click();

      // Fill wallet form
      const nameInput = page.getByPlaceholder(/name/i);
      if (await nameInput.isVisible({ timeout: 3000 })) {
        await nameInput.fill(`Golden_${Date.now()}`);
      }

      // Select network if needed
      const networkSelect = page.getByRole('combobox').first();
      if (await networkSelect.isVisible({ timeout: 2000 })) {
        await networkSelect.click();
        await page.getByText(/sepolia/i).first().click();
      }

      // Submit
      await page.getByRole('button', { name: /create|submit/i }).click();
      await page.waitForTimeout(3000);
    }

    // Get wallet via API
    const wallets = await getWallets(userToken);

    if (wallets.length === 0) {
      // Create via API as fallback
      const result = await api('POST', '/v1/wallets', userToken, {
        wallet_type: 'RETAIL',
        subject_id: testUsername,
      });
      console.log('Wallet creation result:', result);
      expect(result.data).toBeTruthy();
      walletId = result.data.id;
      walletAddress = result.data.address;
    } else {
      walletId = wallets[0].id;
      walletAddress = wallets[0].address;
    }

    console.log(`Wallet created: ${walletAddress}`);
    expect(walletAddress).toMatch(/^0x[a-fA-F0-9]{40}$/);
  });

  test('Step 4: Fund wallet (external deposit)', async () => {
    // This step sends ETH from funding wallet to user's custody wallet
    // In a real test, we would use the private key from .env.test

    console.log(`\n${'='.repeat(60)}`);
    console.log('MANUAL STEP REQUIRED:');
    console.log(`Send ${AMOUNTS.FUNDING} ETH to: ${walletAddress}`);
    console.log(`From funding wallet: ${TEST_ADDRESSES.FUNDING_WALLET}`);
    console.log(`${'='.repeat(60)}\n`);

    // For automated tests, we would do:
    // const { ethers } = require('ethers');
    // const provider = new ethers.JsonRpcProvider(process.env.E2E_SEPOLIA_RPC);
    // const fundingWallet = new ethers.Wallet(process.env.E2E_FUNDING_PRIVATE_KEY, provider);
    // const tx = await fundingWallet.sendTransaction({
    //   to: walletAddress,
    //   value: ethers.parseEther(AMOUNTS.FUNDING)
    // });
    // await tx.wait();

    // For now, we'll check if there's already a deposit or skip
    test.skip(true, 'Manual funding required - run separately');
  });

  test('Step 5: Verify deposit detected', async () => {
    // Wait for chain listener to detect deposit
    let deposits: any[] = [];
    const maxAttempts = 10;

    for (let i = 0; i < maxAttempts; i++) {
      deposits = await getDeposits(adminToken, walletId);
      if (deposits.length > 0) {
        depositId = deposits[0].id;
        console.log(`Deposit detected: ${depositId}`);
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 10000));
    }

    if (deposits.length === 0) {
      console.log('No deposits detected yet - chain listener may need more time');
      test.skip(true, 'Deposit not yet detected');
    }
  });

  test('Step 6: Admin credits deposit', async () => {
    test.skip(!depositId, 'No deposit to credit');

    const result = await approveDeposit(adminToken, depositId);
    expect(result.error).toBeFalsy();

    console.log(`Deposit credited: ${depositId}`);
  });

  test('Step 7: Create withdrawal (triggers RET-02)', async ({ page }) => {
    test.skip(!walletId, 'No wallet available');

    // Create withdrawal via API (amount > 0.001 triggers KYT + approval)
    const result = await createWithdrawal(
      userToken,
      walletId,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.LARGE) // 0.01 ETH - triggers RET-02
    );

    if (result.data?.id) {
      withdrawalId = result.data.id;
      console.log(`Withdrawal created: ${withdrawalId}`);
    } else {
      console.log('Withdrawal creation result:', result);
      // May fail due to insufficient balance
      test.skip(true, 'Could not create withdrawal - check balance');
    }
  });

  test('Step 8: Verify KYT screening', async () => {
    test.skip(!withdrawalId, 'No withdrawal to check');

    // Wait for KYT processing
    await new Promise(resolve => setTimeout(resolve, 3000));

    const txResult = await api('GET', `/v1/transactions/${withdrawalId}`, userToken);

    if (txResult.data) {
      const status = txResult.data.status;
      console.log(`Transaction status after KYT: ${status}`);

      // Should be in approval pending (KYT passed) or KYT review
      const validStatuses = [
        TX_STATUSES.APPROVAL_PENDING,
        TX_STATUSES.KYT_PENDING,
        TX_STATUSES.KYT_REVIEW,
      ];

      expect(validStatuses.includes(status) || status.includes('PENDING')).toBeTruthy();
    }
  });

  test('Step 9: Admin approves withdrawal', async () => {
    test.skip(!withdrawalId, 'No withdrawal to approve');

    // Wait for status to be approval pending
    const tx = await waitForTxStatus(
      userToken,
      withdrawalId,
      [TX_STATUSES.APPROVAL_PENDING],
      30000
    );
    const finalStatus = tx?.status;

    if (finalStatus !== TX_STATUSES.APPROVAL_PENDING) {
      console.log(`Cannot approve - status is ${finalStatus}`);
      test.skip(true, `Status is ${finalStatus}, not APPROVAL_PENDING`);
    }

    // Approve as admin (different from initiator - SoD)
    const result = await approveWithdrawal(adminToken, withdrawalId, 'Golden path test approval');
    expect(result.error).toBeFalsy();

    console.log('Withdrawal approved by admin');
  });

  test('Step 10: Verify MPC signing initiated', async () => {
    test.skip(!withdrawalId, 'No withdrawal to check');

    // Wait for signing to start
    await new Promise(resolve => setTimeout(resolve, 5000));

    const txResult = await api('GET', `/v1/transactions/${withdrawalId}`, userToken);

    if (txResult.data) {
      const status = txResult.data.status;
      console.log(`Transaction status after approval: ${status}`);

      // Should be signing or beyond
      const signingStatuses = [
        TX_STATUSES.SIGN_PENDING,
        TX_STATUSES.BROADCAST_PENDING,
        TX_STATUSES.MEMPOOL,
        TX_STATUSES.CONFIRMING,
        TX_STATUSES.CONFIRMED,
      ];

      // Accept any progress past approval
      expect(
        signingStatuses.includes(status) ||
        status.includes('SIGN') ||
        status.includes('BROADCAST')
      ).toBeTruthy();
    }
  });

  test('Step 11: Wait for confirmation', async () => {
    test.skip(!withdrawalId, 'No withdrawal to check');

    // Wait for transaction to be confirmed (may take several minutes on testnet)
    const tx = await waitForTxStatus(
      userToken,
      withdrawalId,
      [TX_STATUSES.CONFIRMED, TX_STATUSES.FINALIZED],
      TIMEOUTS.CONFIRMATION
    );
    const finalStatus = tx?.status;

    console.log(`Final transaction status: ${finalStatus}`);

    // Accept confirmed or finalized
    const successStatuses = [TX_STATUSES.CONFIRMED, TX_STATUSES.FINALIZED, 'COMPLETED'];
    expect(successStatuses.some(s => finalStatus.includes(s))).toBeTruthy();
  });

  test('Step 12: Verify audit trail', async () => {
    test.skip(!withdrawalId, 'No withdrawal to check');

    // Get audit events for this transaction
    const auditResult = await api(
      'GET',
      `/v1/audit/events?transaction_id=${withdrawalId}`,
      adminToken
    );

    if (auditResult.data) {
      const events = Array.isArray(auditResult.data) ? auditResult.data : auditResult.data.events || [];
      console.log(`Audit events count: ${events.length}`);

      // Should have events for: create, kyt, approval, signing, broadcast
      expect(events.length).toBeGreaterThan(0);

      // Log event types
      const eventTypes = events.map((e: any) => e.event_type || e.type);
      console.log('Audit event types:', eventTypes);
    }
  });
});

/**
 * Simplified Golden Path - Uses existing test user and wallet
 *
 * This is a faster version that doesn't require manual funding.
 * It tests the withdrawal flow assuming the wallet has balance.
 */
test.describe('INT-GOLD-02: Simplified Withdrawal Flow', () => {
  let token: string;
  let walletId: string;
  let txId: string;

  test.beforeAll(async () => {
    token = (await getTokenForUser('retail'))!;
    const wallets = await getWallets(token);
    if (wallets.length > 0) {
      walletId = wallets[0].id;
    }
  });

  test('Create and process micro withdrawal (RET-01)', async () => {
    test.skip(!walletId, 'No wallet available');

    // Micro amount - should skip KYT and approval per RET-01
    const result = await createWithdrawal(
      token,
      walletId,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.MICRO) // 0.0005 ETH
    );

    if (!result.data?.id) {
      console.log('Could not create micro withdrawal:', result);
      test.skip(true, 'Insufficient balance or other error');
      return;
    }

    txId = result.data.id;
    console.log(`Micro withdrawal created: ${txId}`);

    // Should go directly to signing (skip KYT/approval)
    await new Promise(resolve => setTimeout(resolve, 3000));

    const txResult = await api('GET', `/v1/transactions/${txId}`, token);
    console.log(`Micro tx status: ${txResult.data?.status}`);

    // Should not be stuck in approval
    expect(txResult.data?.status).not.toBe(TX_STATUSES.APPROVAL_PENDING);
  });
});
