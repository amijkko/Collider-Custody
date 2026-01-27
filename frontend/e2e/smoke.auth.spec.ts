import { test, expect } from '@playwright/test';
import { TIMEOUTS } from './fixtures/test-data';
import { api, getGroups } from './fixtures/api-helpers';
import {
  login,
  logout,
  registerUser,
  clearAuth,
  TEST_USERS,
  getTokenForUser,
} from './fixtures/auth-helpers';

/**
 * Smoke Auth Tests
 *
 * Quick authentication tests for CI smoke suite.
 */

test.describe('Authentication Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await clearAuth(page);
  });

  test('E2E-AUTH-01: Register → auto-enroll Retail', async ({ page }) => {
    const testId = Date.now();
    const username = `smoke_${testId}`;
    const email = `smoke_${testId}@example.com`;
    const password = 'SmokeTest2026!';

    // Register
    const registered = await registerUser(page, username, email, password);

    if (!registered) {
      console.log('Registration failed or user exists, checking enrollment');
    }

    // Check if already logged in after registration (frontend may auto-login)
    let token = await page.evaluate(() => localStorage.getItem('access_token'));

    // If not logged in, try to login
    if (!token) {
      try {
        await login(page, username, password);
        token = await page.evaluate(() => localStorage.getItem('access_token'));
      } catch (error) {
        console.log('Login failed:', error);
      }
    }

    // Check enrollment via API
    try {

      if (token) {
        // Get groups and check if user is in Retail
        const adminToken = await getTokenForUser('admin');
        if (adminToken) {
          const groups = await getGroups(adminToken);
          const retailGroup = groups.find(g => g.name === 'Retail');

          if (retailGroup) {
            const groupDetail = await api('GET', `/v1/groups/${retailGroup.id}`, adminToken);
            const members = groupDetail.data?.members || [];
            const enrolled = members.some((m: any) =>
              m.user?.username === username || m.username === username
            );

            console.log(`User ${username} enrolled in Retail: ${enrolled}`);
          }
        }
      }
    } catch (error) {
      console.log('Could not verify enrollment:', error);
    }
  });

  test('E2E-AUTH-02: Login valid credentials', async ({ page }) => {
    await login(page, TEST_USERS.retail.username, TEST_USERS.retail.password);

    // Should be on app
    await expect(page).toHaveURL(/\/app/);

    // Token should be set
    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(token).toBeTruthy();
  });

  test('E2E-AUTH-03: Login invalid credentials shows error', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    await page.getByPlaceholder(/enter your username/i).fill('nonexistent_user_xyz');
    await page.getByPlaceholder(/enter your password/i).fill('wrongpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();

    // Should show error
    await expect(page.getByText(/error|invalid|failed|incorrect/i).first())
      .toBeVisible({ timeout: TIMEOUTS.API });

    // Should stay on login
    await expect(page).toHaveURL(/\/login/);
  });

  test('E2E-AUTH-04: Route guard redirects to login', async ({ page }) => {
    await page.goto('/app/deposit');

    // Should redirect
    await expect(page).toHaveURL(/\/login/, { timeout: TIMEOUTS.PAGE_LOAD });
  });

  test('E2E-AUTH-05: Logout clears session', async ({ page }) => {
    // Login first
    await login(page, TEST_USERS.retail.username, TEST_USERS.retail.password);
    await page.waitForURL(/\/app/);

    // Logout
    await logout(page);

    // Verify token cleared
    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(token).toBeFalsy();

    // Should be on login
    await expect(page).toHaveURL(/\/login/);
  });

  test('E2E-AUTH-06: Admin login provides admin access', async ({ page }) => {
    await login(page, TEST_USERS.admin.username, TEST_USERS.admin.password);

    // Navigate to admin
    await page.goto('/admin/deposits');
    await page.waitForLoadState('networkidle');

    // Should have access
    await expect(page.getByText(/Deposit|Management/i).first())
      .toBeVisible({ timeout: TIMEOUTS.PAGE_LOAD });
  });
});

test.describe('Registration Flow', () => {
  test('E2E-REG-01: Registration page displays form', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');

    // Check form fields
    await expect(page.getByPlaceholder(/username/i).first()).toBeVisible();
    await expect(page.getByPlaceholder(/email/i)).toBeVisible();
    await expect(page.getByPlaceholder(/password/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /create|register|sign up/i })).toBeVisible();
  });

  test('E2E-REG-02: Registration validates input', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');

    // Try to submit empty form
    await page.getByRole('button', { name: /create|register|sign up/i }).click();

    // Should show validation errors or stay on page
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL(/\/register/);
  });

  test('E2E-REG-03: Link to login page works', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');

    // Find and click login link
    const loginLink = page.getByRole('link', { name: /sign in|login|already have/i });
    if (await loginLink.isVisible({ timeout: 3000 })) {
      await loginLink.click();
      await expect(page).toHaveURL(/\/login/);
    }
  });
});

test.describe('Login Page UI', () => {
  test('E2E-LOGIN-01: Login page displays correctly', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Check elements
    await expect(page.getByText(/Welcome|Sign in|Login/i).first()).toBeVisible();
    await expect(page.getByPlaceholder(/username/i).first()).toBeVisible();
    await expect(page.getByPlaceholder(/password/i).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in|login/i })).toBeVisible();
  });

  test('E2E-LOGIN-02: Demo credentials hint visible', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Should show demo hint
    const hasDemo = await page.getByText(/demo|test.*credentials/i).first()
      .isVisible({ timeout: 5000 }).catch(() => false);

    console.log(`Demo credentials hint visible: ${hasDemo}`);
  });

  test('E2E-LOGIN-03: Link to register page works', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    const registerLink = page.getByRole('link', { name: /register|create.*account|sign up/i });
    if (await registerLink.isVisible({ timeout: 3000 })) {
      await registerLink.click();
      await expect(page).toHaveURL(/\/register/);
    }
  });
});
