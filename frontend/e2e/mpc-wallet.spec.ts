import { test, expect } from '@playwright/test';

/**
 * MPC Wallet Creation Test
 *
 * Tests the full DKG (Distributed Key Generation) flow:
 * 1. Login
 * 2. Open create wallet modal
 * 3. Select MPC wallet type
 * 4. Enter password
 * 5. Wait for DKG to complete
 * 6. Verify wallet address is displayed
 */

// User without MPC wallet
const TEST_USER = {
  username: 'test10',
  password: 'demo123456',
};

const MPC_PASSWORD = 'TestMpcPass2026!'; // At least 12 chars

test.describe('MPC Wallet Creation', () => {
  test('Create MPC wallet via DKG', async ({ page }) => {
    // Increase timeout for DKG (can take up to 2 minutes)
    test.setTimeout(180000);

    // Enable console logging
    page.on('console', msg => {
      const text = msg.text();
      if (text.includes('[MPC]') || text.includes('[TSS-WASM]')) {
        console.log(`[Browser] ${text}`);
      }
    });

    page.on('pageerror', err => {
      console.error(`[Browser Error] ${err.message}`);
    });

    // Step 1: Login
    console.log('Step 1: Logging in as admin2...');
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    await page.getByPlaceholder(/enter your username/i).fill(TEST_USER.username);
    await page.getByPlaceholder(/enter your password/i).fill(TEST_USER.password);
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL(/\/(app|admin)/, { timeout: 30000 });
    console.log('Logged in successfully');

    // Step 2: Navigate to dashboard and find create wallet button
    console.log('Step 2: Looking for Create Wallet button...');
    await page.goto('/app');
    await page.waitForLoadState('networkidle');

    // Click Create Wallet button
    const createWalletBtn = page.getByRole('button', { name: /create.*wallet|new.*wallet/i }).first();

    // If not visible, try looking in other places
    if (!await createWalletBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Try finding it as a link or different button
      const altBtn = page.locator('button, a').filter({ hasText: /create|new/i }).first();
      if (await altBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await altBtn.click();
      } else {
        console.log('Create wallet button not found, user may already have a wallet');
        // Check if wallet exists
        const walletInfo = page.getByText(/0x[a-fA-F0-9]{4,}/i).first();
        if (await walletInfo.isVisible({ timeout: 5000 }).catch(() => false)) {
          console.log('User already has a wallet');
          return;
        }
        throw new Error('Cannot find create wallet button');
      }
    } else {
      await createWalletBtn.click();
    }

    // Step 3: Select MPC wallet type (already selected by default)
    console.log('Step 3: MPC wallet is selected by default, clicking Continue...');
    await page.waitForTimeout(500);

    // Click Continue
    const continueBtn = page.getByRole('button', { name: /continue/i });
    await expect(continueBtn).toBeVisible({ timeout: 5000 });
    await continueBtn.click();
    console.log('Selected MPC wallet, proceeding to password');

    // Step 4: Enter password
    console.log('Step 4: Entering password...');
    await page.waitForTimeout(500);

    // Fill password fields
    const passwordField = page.getByPlaceholder(/create.*password|strong.*password/i);
    const confirmField = page.getByPlaceholder(/confirm/i);

    await expect(passwordField).toBeVisible({ timeout: 5000 });
    await passwordField.fill(MPC_PASSWORD);
    await confirmField.fill(MPC_PASSWORD);

    // Click Create Wallet button
    const createBtn = page.getByRole('button', { name: /create.*wallet/i });
    await expect(createBtn).toBeEnabled({ timeout: 3000 });
    await createBtn.click();
    console.log('Password entered, starting DKG...');

    // Step 5: Wait for DKG to complete
    console.log('Step 5: Waiting for DKG to complete...');

    // Should show progress indicator (keygen step)
    await expect(page.getByText(/generating|creating|DKG|progress/i).first()).toBeVisible({ timeout: 15000 });
    console.log('DKG started, waiting for completion...');

    // Wait for the "complete" step with wallet address - this can take up to 2 minutes
    // Look specifically for the success screen with "Wallet Created!" heading
    const successTitle = page.getByRole('heading', { name: 'Wallet Created!' });
    await expect(successTitle).toBeVisible({ timeout: 120000 });
    console.log('DKG completed!');

    // Step 6: Verify wallet address is displayed
    console.log('Step 6: Verifying wallet address...');
    const walletAddress = page.getByText(/0x[a-fA-F0-9]{40}/i).first();
    await expect(walletAddress).toBeVisible({ timeout: 10000 });

    const addressText = await walletAddress.textContent();
    console.log(`Wallet created with address: ${addressText}`);

    // Close modal
    const doneBtn = page.getByRole('button', { name: /done|close/i });
    if (await doneBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await doneBtn.click();
    }

    console.log('MPC Wallet creation test completed successfully!');
  });
});
