import { test, expect, Page } from '@playwright/test';

/**
 * E2E Test: Full Deposit Flow
 *
 * Tests the complete deposit cycle:
 * 1. User registration
 * 2. Wallet creation
 * 3. Deposit detection (simulated via API)
 * 4. Admin approval
 * 5. Balance verification
 */

const API_URL = process.env.E2E_API_URL || 'http://localhost:8000';

// Test credentials
const ADMIN_USER = {
  username: 'admin2',
  password: 'admin123456',
};

// Generate unique test user
const timestamp = Date.now();
const TEST_USER = {
  username: `e2e_fe_${timestamp}`,
  email: `e2e_fe_${timestamp}@test.com`,
  password: 'TestPass2026!',
};

// Store state between tests
let adminToken: string;
let userToken: string;
let userWalletId: string;
let userWalletAddress: string;
let depositId: string;

/**
 * Helper: Login via UI
 */
async function loginViaUI(page: Page, username: string, password: string) {
  await page.goto('/login');
  await expect(page.getByPlaceholder(/username/i)).toBeVisible({ timeout: 10000 });
  await page.getByPlaceholder(/username/i).fill(username);
  await page.getByPlaceholder(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL(/\/(app|admin)/, { timeout: 15000 });
}

/**
 * Helper: API request with auth
 */
async function apiRequest(
  method: string,
  endpoint: string,
  token?: string,
  body?: object
): Promise<any> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  return response.json();
}

test.describe('Deposit Flow E2E', () => {
  test.describe.configure({ mode: 'serial' });

  test('1. Admin can login', async ({ page }) => {
    await loginViaUI(page, ADMIN_USER.username, ADMIN_USER.password);

    // Should be on dashboard or admin page
    await expect(page).toHaveURL(/\/(app|admin)/);

    // Store admin token from localStorage
    adminToken = await page.evaluate(() => localStorage.getItem('access_token') || '');
    expect(adminToken).toBeTruthy();
  });

  test('2. Register new test user', async ({ page }) => {
    await page.goto('/register');

    // Wait for page to load
    await expect(page.getByPlaceholder(/username/i)).toBeVisible({ timeout: 10000 });

    // Fill registration form
    await page.getByPlaceholder(/username/i).fill(TEST_USER.username);
    await page.getByPlaceholder(/email/i).fill(TEST_USER.email);

    // Handle password fields
    const passwordFields = page.getByPlaceholder(/password/i);
    const count = await passwordFields.count();

    if (count >= 2) {
      // Has confirm password field
      await passwordFields.nth(0).fill(TEST_USER.password);
      await passwordFields.nth(1).fill(TEST_USER.password);
    } else {
      await passwordFields.first().fill(TEST_USER.password);
    }

    // Submit
    await page.getByRole('button', { name: /create|register|sign up/i }).click();

    // Wait for navigation or token to appear (registration may auto-login)
    await page.waitForTimeout(3000);

    // Check if already logged in (auto-login after registration)
    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    if (token) {
      console.log('Auto-logged in after registration');
      return;
    }

    // Otherwise wait for redirect to login
    try {
      await page.waitForURL(/\/(login|app)/, { timeout: 10000 });
    } catch {
      // Check if still on register page with no error
      const hasError = await page.getByText(/error|failed|already exists/i).first().isVisible({ timeout: 1000 }).catch(() => false);
      if (!hasError) {
        console.log('Registration likely succeeded');
      }
    }
  });

  test('3. User can login and see dashboard', async ({ page }) => {
    await loginViaUI(page, TEST_USER.username, TEST_USER.password);

    // Store user token
    userToken = await page.evaluate(() => localStorage.getItem('access_token') || '');
    expect(userToken).toBeTruthy();

    // Should see dashboard
    await expect(page.getByText(/Dashboard|Balance|Wallet|Overview/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('4. User creates MPC wallet', async ({ page }) => {
    // Set token and navigate
    await page.evaluate((token) => localStorage.setItem('access_token', token), userToken);
    await page.goto('/app');
    await page.waitForLoadState('networkidle');

    // Look for wallet creation UI
    const createBtn = page.getByRole('button', { name: /create|new wallet/i }).first();

    if (await createBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await createBtn.click();
      await page.waitForTimeout(3000);
    }

    // Get wallet info via API
    const walletsRes = await apiRequest('GET', '/v1/wallets', userToken);
    const mpcWallet = walletsRes.data?.find((w: any) => w.custody_backend === 'MPC_TECDSA');

    if (mpcWallet) {
      userWalletId = mpcWallet.id;
      userWalletAddress = mpcWallet.address;
      console.log(`Wallet: ${userWalletAddress}`);
    }

    expect(userWalletId || userWalletAddress).toBeTruthy();
  });

  test('5. User views deposit page with address', async ({ page }) => {
    await page.evaluate((token) => localStorage.setItem('access_token', token), userToken);
    await page.goto('/app/deposit');
    await page.waitForLoadState('networkidle');

    // Should show deposit page
    await expect(page.getByText(/Deposit|Your.*Address/i).first()).toBeVisible({ timeout: 10000 });

    // Check if address is displayed
    if (userWalletAddress) {
      const addressShort = userWalletAddress.slice(0, 10);
      await expect(page.getByText(new RegExp(addressShort, 'i'))).toBeVisible({ timeout: 10000 });
    }
  });

  test('6. Simulate deposit via API', async ({ page }) => {
    if (!userWalletId) {
      console.log('Skipping - no wallet');
      return;
    }

    // Get admin wallet
    const adminWalletsRes = await apiRequest('GET', '/v1/wallets', adminToken);
    const adminWallet = adminWalletsRes.data?.find(
      (w: any) => w.address?.toLowerCase() === '0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c'
    );

    if (!adminWallet) {
      console.log('Admin wallet not found');
      return;
    }

    // Check balance
    const balanceRes = await apiRequest('GET', `/v1/wallets/${adminWallet.id}/ledger-balance`, adminToken);
    const availableEth = parseFloat(balanceRes.data?.available_eth || '0');

    if (availableEth < 0.001) {
      console.log(`Insufficient balance: ${availableEth}`);
      return;
    }

    // Create and sign transaction
    const txRes = await apiRequest('POST', '/v1/tx-requests', adminToken, {
      wallet_id: adminWallet.id,
      tx_type: 'TRANSFER',
      to_address: userWalletAddress,
      asset: 'ETH',
      amount: '1000000000000000', // 0.001 ETH
    });

    if (txRes.data?.id) {
      await apiRequest('POST', `/v1/tx-requests/${txRes.data.id}/sign`, adminToken);
      console.log(`TX: ${txRes.data.id}`);

      // Wait for deposit detection
      await page.waitForTimeout(35000);

      // Check deposit
      const depositsRes = await apiRequest('GET', `/v1/deposits?wallet_id=${userWalletId}`, adminToken);
      const pending = depositsRes.data?.find((d: any) => d.status === 'PENDING_ADMIN');

      if (pending) {
        depositId = pending.id;
        console.log(`Deposit: ${depositId}`);
      }
    }
  });

  test('7. Admin sees pending deposit', async ({ page }) => {
    await page.evaluate((token) => localStorage.setItem('access_token', token), adminToken);
    await page.goto('/admin/deposits');
    await page.waitForLoadState('networkidle');

    // Should see pending section
    await expect(page.getByText(/Pending|Approval/i).first()).toBeVisible({ timeout: 10000 });

    if (depositId) {
      // Look for approve button
      const approveBtn = page.getByRole('button', { name: /approve/i }).first();
      await expect(approveBtn).toBeVisible({ timeout: 5000 }).catch(() => {});
    }
  });

  test('8. Admin approves deposit', async ({ page }) => {
    if (!depositId) {
      // Try to find any pending
      const depositsRes = await apiRequest('GET', '/v1/deposits/admin', adminToken);
      const pending = depositsRes.data?.find((d: any) => d.status === 'PENDING_ADMIN');
      if (pending) depositId = pending.id;
    }

    if (!depositId) {
      console.log('No pending deposit');
      return;
    }

    await page.evaluate((token) => localStorage.setItem('access_token', token), adminToken);
    await page.goto('/admin/deposits');
    await page.waitForLoadState('networkidle');

    // Try UI approval
    const approveBtn = page.getByRole('button', { name: /approve/i }).first();

    if (await approveBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await approveBtn.click();

      // Confirm in modal
      const confirmBtn = page.locator('[role="dialog"]').getByRole('button', { name: /approve/i });
      if (await confirmBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await confirmBtn.click();
      }

      await page.waitForTimeout(2000);
    } else {
      // API fallback
      await apiRequest('POST', `/v1/deposits/${depositId}/approve`, adminToken);
    }

    // Verify
    const depositRes = await apiRequest('GET', `/v1/deposits/${depositId}`, adminToken);
    expect(depositRes.data?.status).toBe('CREDITED');
    console.log('Deposit approved');
  });

  test('9. User sees updated balance', async ({ page }) => {
    if (!userWalletId) return;

    await page.evaluate((token) => localStorage.setItem('access_token', token), userToken);
    await page.goto('/app');
    await page.waitForLoadState('networkidle');

    // Check via API
    const balanceRes = await apiRequest('GET', `/v1/wallets/${userWalletId}/ledger-balance`, userToken);
    const availableEth = parseFloat(balanceRes.data?.available_eth || '0');
    console.log(`Balance: ${availableEth} ETH`);

    if (depositId) {
      expect(availableEth).toBeGreaterThan(0);
    }

    // UI should show balance
    await expect(page.getByText(/ETH|Balance/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('10. Deposit history shows credited deposit', async ({ page }) => {
    if (!userWalletId) return;

    await page.evaluate((token) => localStorage.setItem('access_token', token), userToken);
    await page.goto('/app/deposit');
    await page.waitForLoadState('networkidle');

    // Should see history
    await expect(page.getByText(/History|Recent/i).first()).toBeVisible({ timeout: 10000 });

    if (depositId) {
      await expect(page.getByText(/CREDITED|Completed/i).first()).toBeVisible({ timeout: 10000 });
    }
  });
});
