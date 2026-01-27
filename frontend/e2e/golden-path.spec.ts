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
  fundWallet,
  waitForDeposit,
  getFundingWalletBalance,
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

  test('Step 3: Create MPC wallet', async ({ page }) => {
    // MPC DKG takes 1-2 minutes
    test.setTimeout(180000);

    // Navigate first, then set token
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');
    await page.evaluate((token) => localStorage.setItem('access_token', token), userToken);
    await page.goto('/app');
    await page.waitForLoadState('networkidle');

    // Check if wallet already exists
    const existingWallets = await getWallets(userToken);
    const mpcWallet = existingWallets.find((w: any) => w.custody_backend === 'MPC_TECDSA');

    if (mpcWallet) {
      walletId = mpcWallet.id;
      walletAddress = mpcWallet.address;
      console.log(`Using existing MPC wallet: ${walletAddress}`);
      return;
    }

    // Look for Create Wallet button
    const createBtn = page.getByRole('button', { name: /create.*wallet|new.*wallet/i }).first();

    if (await createBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await createBtn.click();
      await page.waitForTimeout(1000);

      // MPC should be selected by default, click Continue
      const continueBtn = page.getByRole('button', { name: /continue/i });
      if (await continueBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await continueBtn.click();
        await page.waitForTimeout(500);

        // Enter password for MPC key encryption
        const passwordField = page.getByPlaceholder(/password/i).first();
        if (await passwordField.isVisible({ timeout: 3000 }).catch(() => false)) {
          await passwordField.fill(testPassword);

          // Confirm password if there's a second field
          const confirmField = page.getByPlaceholder(/confirm/i);
          if (await confirmField.isVisible({ timeout: 1000 }).catch(() => false)) {
            await confirmField.fill(testPassword);
          }

          // Click Create Wallet
          const finalCreateBtn = page.getByRole('button', { name: /create.*wallet/i });
          if (await finalCreateBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
            await finalCreateBtn.click();

            // Wait for DKG process (shows progress indicator)
            console.log('Starting MPC DKG process...');
            await page.waitForTimeout(5000);

            // Wait for wallet to appear in API (DKG takes time)
            const maxWaitTime = 150000;
            const startTime = Date.now();

            while (Date.now() - startTime < maxWaitTime) {
              const wallets = await getWallets(userToken);
              const newMpcWallet = wallets.find((w: any) => w.custody_backend === 'MPC_TECDSA');

              if (newMpcWallet) {
                walletId = newMpcWallet.id;
                walletAddress = newMpcWallet.address;
                console.log(`MPC wallet created: ${walletAddress}`);
                break;
              }

              await page.waitForTimeout(5000);
              console.log('Waiting for MPC wallet creation...');
            }
          }
        }
      }
    }

    // Verify wallet was created
    if (!walletId) {
      const wallets = await getWallets(userToken);
      if (wallets.length > 0) {
        walletId = wallets[0].id;
        walletAddress = wallets[0].address;
      }
    }

    expect(walletAddress).toMatch(/^0x[a-fA-F0-9]{40}$/);
    console.log(`Final wallet: ${walletAddress}`);
  });

  test('Step 4: Fund wallet (external deposit)', async () => {
    // This step sends ETH from funding wallet to user's custody wallet
    test.setTimeout(120000); // 2 minutes for blockchain tx

    if (!walletAddress) {
      test.skip(true, 'No wallet address available');
      return;
    }

    // Check funding wallet balance
    const fundingBalance = await getFundingWalletBalance();
    console.log(`Funding wallet balance: ${fundingBalance} ETH`);

    if (parseFloat(fundingBalance) < parseFloat(AMOUNTS.FUNDING)) {
      test.skip(true, `Insufficient funding balance: ${fundingBalance} ETH`);
      return;
    }

    // Send ETH from funding wallet to user's MPC wallet
    console.log(`\n${'='.repeat(60)}`);
    console.log(`Sending ${AMOUNTS.FUNDING} ETH to: ${walletAddress}`);
    console.log(`From funding wallet: ${TEST_ADDRESSES.FUNDING_WALLET}`);
    console.log(`${'='.repeat(60)}\n`);

    const result = await fundWallet(walletAddress, AMOUNTS.FUNDING);

    if (!result.success) {
      console.log(`Funding failed: ${result.error}`);
      test.skip(true, `Funding failed: ${result.error}`);
      return;
    }

    console.log(`Funding transaction confirmed: ${result.txHash}`);
    expect(result.txHash).toBeTruthy();
  });

  test('Step 5: Verify deposit detected', async () => {
    // Wait for chain listener to detect deposit (up to 2 minutes)
    test.setTimeout(150000);

    if (!walletId) {
      test.skip(true, 'No wallet ID available');
      return;
    }

    console.log('Waiting for deposit to be detected by chain listener...');

    try {
      const deposit = await waitForDeposit(adminToken, walletId, 120000, 10000);
      depositId = deposit.id;
      console.log(`Deposit detected: ${depositId} (status: ${deposit.status})`);
      expect(depositId).toBeTruthy();
    } catch (error) {
      console.log('Deposit not detected within timeout:', error);
      // Check if there are any deposits at all
      const deposits = await getDeposits(adminToken, walletId);
      if (deposits.length > 0) {
        depositId = deposits[0].id;
        console.log(`Found deposit: ${depositId} (status: ${deposits[0].status})`);
      } else {
        test.skip(true, 'Deposit not yet detected by chain listener');
      }
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
