/**
 * Authentication Helpers for E2E Tests
 *
 * UI-based login/logout and session management helpers.
 */

import { Page, expect } from '@playwright/test';
import { loginApi } from './api-helpers';

/**
 * Test users with different roles
 */
export const TEST_USERS = {
  admin: {
    username: 'admin2',
    password: 'admin123456',
    role: 'ADMIN',
  },
  compliance: {
    username: 'admin2', // Use admin for compliance tests
    password: 'admin123456',
    role: 'COMPLIANCE',
  },
  viewer: {
    username: 'test_retail',
    password: 'RetailPass2026',
    role: 'VIEWER',
  },
  retail: {
    username: 'demo',
    password: 'demo123456',
    role: 'OPERATOR',
  },
};

/**
 * Login via UI
 */
export async function login(page: Page, username: string, password: string): Promise<void> {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  // Fill credentials
  await page.getByPlaceholder(/enter your username/i).fill(username);
  await page.getByPlaceholder(/enter your password/i).fill(password);

  // Click sign in button
  const signInBtn = page.getByRole('button', { name: /sign in/i });
  await signInBtn.waitFor({ state: 'visible' });

  // Use Promise.all to click and wait for navigation simultaneously
  await Promise.all([
    page.waitForURL(url => url.pathname.startsWith('/app') || url.pathname.startsWith('/admin'), {
      timeout: 30000,
    }),
    signInBtn.click(),
  ]);
}

/**
 * Login as admin via UI
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  await login(page, TEST_USERS.admin.username, TEST_USERS.admin.password);
}

/**
 * Login as retail user via UI
 */
export async function loginAsRetail(page: Page): Promise<void> {
  await login(page, TEST_USERS.retail.username, TEST_USERS.retail.password);
}

/**
 * Login as compliance user via UI
 */
export async function loginAsCompliance(page: Page): Promise<void> {
  await login(page, TEST_USERS.compliance.username, TEST_USERS.compliance.password);
}

/**
 * Login as viewer via UI
 */
export async function loginAsViewer(page: Page): Promise<void> {
  await login(page, TEST_USERS.viewer.username, TEST_USERS.viewer.password);
}

/**
 * Set auth token directly (faster than UI login)
 */
export async function setAuthToken(page: Page, token: string): Promise<void> {
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');
  await page.evaluate((t) => localStorage.setItem('access_token', t), token);
}

/**
 * Get auth token from page
 */
export async function getAuthToken(page: Page): Promise<string | null> {
  return page.evaluate(() => localStorage.getItem('access_token'));
}

/**
 * Logout via UI
 */
export async function logout(page: Page): Promise<void> {
  // Try to find and click logout button
  const logoutBtn = page.getByRole('button', { name: /logout|sign out/i })
    .or(page.getByText(/logout|sign out/i));

  // Might need to open user menu first
  const userMenu = page.locator('[data-testid="user-menu"]')
    .or(page.getByRole('button').filter({ hasText: /@|user/i }));

  if (await userMenu.first().isVisible({ timeout: 3000 }).catch(() => false)) {
    await userMenu.first().click();
  }

  if (await logoutBtn.first().isVisible({ timeout: 3000 }).catch(() => false)) {
    await logoutBtn.first().click();
    await page.waitForURL(/\/login/, { timeout: 10000 });
  } else {
    // Fallback: clear token and navigate
    await page.evaluate(() => localStorage.removeItem('access_token'));
    await page.goto('/login');
  }
}

/**
 * Clear auth state
 */
export async function clearAuth(page: Page): Promise<void> {
  // Navigate to login page first to have access to localStorage
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');
  await page.evaluate(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
  });
}

/**
 * Register a new user via UI
 */
export async function registerUser(
  page: Page,
  username: string,
  email: string,
  password: string
): Promise<boolean> {
  await page.goto('/register');
  await page.waitForLoadState('networkidle');

  await page.getByPlaceholder(/choose a username/i).fill(username);
  await page.getByPlaceholder(/enter your email/i).fill(email);
  await page.getByPlaceholder(/create a password/i).fill(password);
  await page.getByPlaceholder(/confirm your password/i).fill(password);

  await page.getByRole('button', { name: /create account/i }).click();

  // Wait for response
  await page.waitForTimeout(3000);

  // Check for success (redirect) or error
  const hasError = await page.getByText(/error|failed|already exists/i).first()
    .isVisible({ timeout: 2000 }).catch(() => false);

  return !hasError;
}

/**
 * Get API token for a test user
 */
export async function getTokenForUser(userKey: keyof typeof TEST_USERS): Promise<string | null> {
  const user = TEST_USERS[userKey];
  return loginApi(user.username, user.password);
}

/**
 * Setup authenticated page with token
 */
export async function setupAuthenticatedPage(
  page: Page,
  userKey: keyof typeof TEST_USERS
): Promise<string> {
  const token = await getTokenForUser(userKey);
  if (!token) {
    throw new Error(`Failed to get token for user: ${userKey}`);
  }

  await setAuthToken(page, token);
  return token;
}

/**
 * Verify user is on authenticated page
 */
export async function verifyAuthenticated(page: Page): Promise<boolean> {
  const token = await getAuthToken(page);
  return !!token;
}

/**
 * Verify user has admin access
 */
export async function verifyAdminAccess(page: Page): Promise<boolean> {
  await page.goto('/admin/deposits');
  await page.waitForLoadState('networkidle');

  // Check if we're still on admin page (not redirected)
  const isAdmin = page.url().includes('/admin');
  const hasContent = await page.getByText(/Deposit|Management/i).first()
    .isVisible({ timeout: 5000 }).catch(() => false);

  return isAdmin && hasContent;
}
