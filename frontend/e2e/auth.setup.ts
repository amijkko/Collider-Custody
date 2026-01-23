import { test as setup, expect } from '@playwright/test';

const API_URL = process.env.E2E_API_URL || 'https://discerning-rebirth-production.up.railway.app';

// Test credentials
export const E2E_ADMIN = {
  username: 'e2e_bot',
  password: 'E2eTestPass2026',
};

// User created by backend E2E test
export const E2E_USER = {
  username: 'e2e_user_1575',
  password: 'TestPass2026!',
};

/**
 * Helper to login via API and get token
 */
export async function loginViaAPI(username: string, password: string): Promise<string> {
  const response = await fetch(`${API_URL}/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    throw new Error(`Login failed: ${response.status}`);
  }

  const data = await response.json();
  return data.data.access_token;
}

/**
 * Helper to create a new user via API
 */
export async function createUserViaAPI(username: string, email: string, password: string): Promise<string> {
  const response = await fetch(`${API_URL}/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Registration failed: ${error.detail}`);
  }

  const data = await response.json();
  return data.data.id;
}

/**
 * Setup: Authenticate as admin user and store state
 */
setup('authenticate as admin', async ({ page }) => {
  // Go to login page
  await page.goto('/login');

  // Fill login form
  await page.fill('input[name="username"]', E2E_ADMIN.username);
  await page.fill('input[name="password"]', E2E_ADMIN.password);

  // Submit
  await page.click('button[type="submit"]');

  // Wait for redirect to dashboard
  await expect(page).toHaveURL(/\/(app|admin)/, { timeout: 10000 });

  // Save storage state
  await page.context().storageState({ path: 'e2e/.auth/admin.json' });
});
