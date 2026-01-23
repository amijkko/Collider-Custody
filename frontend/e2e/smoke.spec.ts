import { test, expect } from '@playwright/test';

/**
 * Smoke Tests - Basic functionality checks
 */

test.describe('Smoke Tests', () => {
  test('homepage loads and redirects to login', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/(login|app|admin)?/);
  });

  test('login page loads correctly', async ({ page }) => {
    await page.goto('/login');

    // Wait for page content
    await expect(page.getByText(/Welcome|Sign in|Collider/i).first()).toBeVisible({ timeout: 15000 });

    // Should have login form elements (using full placeholder text)
    await expect(page.getByPlaceholder(/enter your username/i)).toBeVisible();
    await expect(page.getByPlaceholder(/enter your password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
  });

  test('register page loads correctly', async ({ page }) => {
    await page.goto('/register');

    // Wait for page content
    await expect(page.getByText(/Create|Register|Sign up/i).first()).toBeVisible({ timeout: 15000 });

    // Should have registration form elements
    await expect(page.getByPlaceholder(/username/i).first()).toBeVisible();
    await expect(page.getByPlaceholder(/email/i)).toBeVisible();
    await expect(page.getByPlaceholder(/password/i).first()).toBeVisible();
  });

  test('login with invalid credentials shows error', async ({ page }) => {
    await page.goto('/login');

    // Wait for page to load
    await expect(page.getByPlaceholder(/enter your username/i)).toBeVisible({ timeout: 15000 });

    // Fill login form
    await page.getByPlaceholder(/enter your username/i).fill('invalid_user_xyz');
    await page.getByPlaceholder(/enter your password/i).fill('invalid_pass_xyz');
    await page.getByRole('button', { name: /sign in/i }).click();

    // Should show error message (toast or inline)
    await expect(page.getByText(/error|invalid|incorrect|failed/i).first()).toBeVisible({ timeout: 15000 });
  });

  test('admin login works', async ({ page }) => {
    await page.goto('/login');

    // Wait for page to load
    await expect(page.getByPlaceholder(/enter your username/i)).toBeVisible({ timeout: 15000 });

    // Fill login form
    await page.getByPlaceholder(/enter your username/i).fill('e2e_bot');
    await page.getByPlaceholder(/enter your password/i).fill('E2eTestPass2026');
    await page.getByRole('button', { name: /sign in/i }).click();

    // Should redirect to dashboard
    await expect(page).toHaveURL(/\/(app|admin)/, { timeout: 20000 });

    // Should show some dashboard content
    await expect(page.getByText(/Dashboard|Balance|Wallet|Overview|Welcome/i).first()).toBeVisible({ timeout: 15000 });
  });

  test('authenticated user can access deposit page', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await expect(page.getByPlaceholder(/enter your username/i)).toBeVisible({ timeout: 15000 });
    await page.getByPlaceholder(/enter your username/i).fill('e2e_bot');
    await page.getByPlaceholder(/enter your password/i).fill('E2eTestPass2026');
    await page.getByRole('button', { name: /sign in/i }).click();

    // Wait for redirect or navigation
    await page.waitForURL(/\/(app|admin)/, { timeout: 30000 });

    // Navigate to deposit
    await page.goto('/app/deposit');
    await page.waitForLoadState('networkidle');

    // Should show deposit page content
    await expect(page.getByText(/Deposit|Address|Receive/i).first()).toBeVisible({ timeout: 15000 });
  });

  test('authenticated admin can access deposits management', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await expect(page.getByPlaceholder(/enter your username/i)).toBeVisible({ timeout: 15000 });
    await page.getByPlaceholder(/enter your username/i).fill('e2e_bot');
    await page.getByPlaceholder(/enter your password/i).fill('E2eTestPass2026');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/(app|admin)/, { timeout: 20000 });

    // Navigate to admin deposits
    await page.goto('/admin/deposits');

    // Should show admin deposits page
    await expect(page.getByText(/Deposit|Management|Pending|Approval/i).first()).toBeVisible({ timeout: 15000 });
  });

  test('API health check', async ({ request }) => {
    const apiUrl = process.env.E2E_API_URL || 'https://discerning-rebirth-production.up.railway.app';

    const response = await request.get(`${apiUrl}/health`);
    expect(response.ok()).toBeTruthy();

    const body = await response.json();
    expect(body.status).toBe('healthy');
  });
});
