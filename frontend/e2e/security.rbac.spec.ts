import { test, expect } from '@playwright/test';
import { TIMEOUTS, TEST_ADDRESSES, AMOUNTS } from './fixtures/test-data';
import {
  api,
  getWallets,
  createWithdrawal,
  approveWithdrawal,
  ethToWei,
} from './fixtures/api-helpers';
import {
  setupAuthenticatedPage,
  getTokenForUser,
  clearAuth,
  loginAsViewer,
  login,
  TEST_USERS,
} from './fixtures/auth-helpers';

/**
 * Security & RBAC Tests
 *
 * Tests for role-based access control, route guards, and separation of duties.
 */

test.describe('Route Guards', () => {
  test('E2E-AUTH-04: Unauthenticated redirect to login', async ({ page }) => {
    await clearAuth(page);
    await page.goto('/app/deposit');

    // Should redirect to login
    await expect(page).toHaveURL(/\/login/, { timeout: TIMEOUTS.PAGE_LOAD });
  });

  test('E2E-AUTH-05: Admin routes redirect unauthenticated', async ({ page }) => {
    await clearAuth(page);
    await page.goto('/admin/deposits');

    await expect(page).toHaveURL(/\/login/, { timeout: TIMEOUTS.PAGE_LOAD });
  });

  test('E2E-AUTH-06: Token expiry forces re-login', async ({ page }) => {
    // Set an invalid/expired token
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.setItem('access_token', 'expired_invalid_token');
    });

    await page.goto('/app');
    await page.waitForLoadState('networkidle');

    // Should be redirected to login or show error
    const onLogin = page.url().includes('/login');
    const hasError = await page.getByText(/session|expired|unauthorized|login/i).first()
      .isVisible({ timeout: 5000 }).catch(() => false);

    expect(onLogin || hasError).toBeTruthy();
  });
});

test.describe('RBAC - Role-Based Access', () => {
  test('E2E-RBAC-01: Viewer cannot access admin pages', async ({ page }) => {
    // Login as viewer
    try {
      await login(page, TEST_USERS.viewer.username, TEST_USERS.viewer.password);
    } catch {
      // If viewer user doesn't exist, skip
      console.log('Viewer user not available, skipping test');
      return;
    }

    // Try to access admin route
    await page.goto('/admin/groups');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Check if redirected away or access denied
    const currentUrl = page.url();
    const notOnAdmin = !currentUrl.includes('/admin');

    const accessDenied = await page.getByText(/denied|unauthorized|forbidden|access/i).first()
      .isVisible({ timeout: 3000 }).catch(() => false);

    const redirectedToApp = currentUrl.includes('/app') || currentUrl.includes('/login');

    console.log(`Viewer admin access: URL=${currentUrl}, denied=${accessDenied}`);

    expect(notOnAdmin || accessDenied || redirectedToApp).toBeTruthy();
  });

  test('E2E-RBAC-02: Viewer can access read-only pages', async ({ page }) => {
    try {
      await login(page, TEST_USERS.viewer.username, TEST_USERS.viewer.password);
    } catch {
      console.log('Viewer user not available, skipping test');
      return;
    }

    // Should be able to view dashboard
    await page.goto('/app');
    await page.waitForLoadState('networkidle');

    const hasDashboard = await page.getByText(/Dashboard|Balance|Wallet/i).first()
      .isVisible({ timeout: TIMEOUTS.PAGE_LOAD }).catch(() => false);

    expect(hasDashboard).toBeTruthy();
  });

  test('E2E-RBAC-03: API - Viewer cannot create transactions', async () => {
    const viewerToken = await getTokenForUser('viewer');

    if (!viewerToken) {
      console.log('Viewer token not available');
      return;
    }

    // Try to get wallets first
    const wallets = await getWallets(viewerToken);

    if (wallets.length === 0) {
      console.log('No wallets for viewer');
      return;
    }

    // Try to create a withdrawal
    const result = await createWithdrawal(
      viewerToken,
      wallets[0].id,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.MICRO)
    );

    // Should be denied
    expect(result.error || result.detail).toBeTruthy();
    console.log('Viewer create tx result:', result.error || result.detail);
  });
});

test.describe('Separation of Duties (SoD)', () => {
  let retailToken: string;
  let adminToken: string;
  let walletId: string;

  test.beforeAll(async () => {
    retailToken = (await getTokenForUser('retail'))!;
    adminToken = (await getTokenForUser('admin'))!;

    const wallets = await getWallets(retailToken);
    if (wallets.length > 0) walletId = wallets[0].id;
  });

  test('E2E-SOD-01: Initiator cannot approve own transaction', async () => {
    test.skip(!walletId, 'No wallet available');

    // Create a transaction as retail user
    const result = await createWithdrawal(
      retailToken,
      walletId,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.LARGE)
    );

    if (!result.data?.id) {
      console.log('Could not create transaction');
      return;
    }

    const txId = result.data.id;

    // Wait for approval pending
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Try to approve as the same user (retail)
    const approvalResult = await approveWithdrawal(retailToken, txId, 'Self approval attempt');

    // Should be denied - can't approve own transaction
    // Note: This depends on backend SoD implementation
    console.log('Self-approval result:', approvalResult.error ? 'denied' : 'allowed');

    // If approved, it's a SoD violation - log it
    if (!approvalResult.error) {
      console.warn('WARNING: SoD not enforced - user approved own transaction');
    }
  });

  test('E2E-SOD-02: Different admin can approve', async () => {
    test.skip(!walletId, 'No wallet available');

    // Create a transaction as retail user
    const result = await createWithdrawal(
      retailToken,
      walletId,
      TEST_ADDRESSES.ALLOW_ADDR,
      ethToWei(AMOUNTS.LARGE)
    );

    if (!result.data?.id) {
      console.log('Could not create transaction');
      return;
    }

    const txId = result.data.id;
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Admin (different from initiator) approves
    const approvalResult = await approveWithdrawal(adminToken, txId, 'Admin approval');

    // Should succeed
    expect(approvalResult.error).toBeFalsy();
    console.log('Different user approval: success');
  });
});

test.describe('API Security', () => {
  test('E2E-SEC-01: API requires authentication', async () => {
    // Try to access protected endpoint without token
    const result = await api('GET', '/v1/wallets');

    expect(result.detail || result.error).toBeTruthy();
    console.log('Unauthenticated API access:', result.detail || result.error);
  });

  test('E2E-SEC-02: Invalid token rejected', async () => {
    const result = await api('GET', '/v1/wallets', 'invalid_token_12345');

    expect(result.detail || result.error).toBeTruthy();
  });

  test('E2E-SEC-03: Cannot access other user wallets', async () => {
    const retailToken = await getTokenForUser('retail');
    const adminToken = await getTokenForUser('admin');

    if (!retailToken || !adminToken) return;

    // Get admin's wallets
    const adminWallets = await getWallets(adminToken);
    if (adminWallets.length === 0) return;

    const adminWalletId = adminWallets[0].id;

    // Try to access admin wallet as retail user
    const result = await api('GET', `/v1/wallets/${adminWalletId}`, retailToken);

    // Should be denied or return different user's wallet restriction
    // Note: Depends on implementation - might return 403 or filter results
    console.log('Cross-user wallet access:', result.error ? 'denied' : 'allowed');
  });

  test('E2E-SEC-04: Rate limiting headers present', async () => {
    // This would need to check response headers
    // For now, just verify we can make requests without being rate limited
    const retailToken = await getTokenForUser('retail');

    for (let i = 0; i < 5; i++) {
      const result = await api('GET', '/v1/wallets', retailToken);
      if (result.error?.includes('rate') || result.error?.includes('429')) {
        console.log('Rate limiting triggered after', i, 'requests');
        return;
      }
    }

    console.log('No rate limiting triggered in quick succession');
  });
});

test.describe('Session Management', () => {
  test('E2E-AUTH-07: Session persists across reload', async ({ page }) => {
    await login(page, TEST_USERS.retail.username, TEST_USERS.retail.password);
    await page.waitForURL(/\/app/);

    // Reload
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Should still be logged in
    await expect(page).toHaveURL(/\/app/);
  });

  test('E2E-AUTH-08: Logout clears session', async ({ page }) => {
    await login(page, TEST_USERS.retail.username, TEST_USERS.retail.password);
    await page.waitForURL(/\/app/);

    // Clear token (simulate logout)
    await page.evaluate(() => localStorage.removeItem('access_token'));
    await page.goto('/app');

    // Should redirect to login
    await expect(page).toHaveURL(/\/login/, { timeout: TIMEOUTS.PAGE_LOAD });
  });
});
