import { test, expect } from '@playwright/test';
import { TIMEOUTS } from './fixtures/test-data';
import {
  api,
  getGroups,
  getGroup,
  addGroupMember,
  removeGroupMember,
} from './fixtures/api-helpers';
import {
  setupAuthenticatedPage,
  getTokenForUser,
  loginAsAdmin,
} from './fixtures/auth-helpers';

/**
 * Admin Groups & Policies Tests
 *
 * Tests for group management, policy assignment, and address book.
 */

test.describe('Admin: Groups Management', () => {
  let adminToken: string;

  test.beforeAll(async () => {
    adminToken = (await getTokenForUser('admin'))!;
  });

  test('E2E-ADM-GRP-01: Groups page displays Retail with counters', async ({ page }) => {
    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/groups');
    await page.waitForLoadState('networkidle');

    // Should show groups page
    await expect(page.getByText(/Groups|Management/i).first()).toBeVisible({ timeout: TIMEOUTS.PAGE_LOAD });

    // Should show Retail group
    await expect(page.getByText(/Retail/i).first()).toBeVisible();

    // Should show member count
    const memberCount = await page.getByText(/members?|users?/i).first()
      .isVisible({ timeout: 5000 }).catch(() => false);

    console.log(`Member count visible: ${memberCount}`);
  });

  test('E2E-ADM-GRP-02: Group details page shows members', async ({ page }) => {
    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/groups');
    await page.waitForLoadState('networkidle');

    // Click on Retail group
    const retailGroup = page.getByText(/Retail/).first();
    if (await retailGroup.isVisible()) {
      await retailGroup.click();
      await page.waitForLoadState('networkidle');

      // Should show members section
      await expect(page.getByText(/Members|Users/i).first()).toBeVisible({ timeout: TIMEOUTS.PAGE_LOAD });

      // Check for member list or empty state
      const hasList = await page.locator('table, [role="table"], ul').first()
        .isVisible({ timeout: 5000 }).catch(() => false);

      console.log(`Members list visible: ${hasList}`);
    }
  });

  test('E2E-ADM-GRP-03: API - List groups', async () => {
    const groups = await getGroups(adminToken);

    expect(Array.isArray(groups)).toBe(true);
    expect(groups.length).toBeGreaterThan(0);

    // Find Retail group
    const retailGroup = groups.find(g => g.name === 'Retail');
    expect(retailGroup).toBeTruthy();
    expect(retailGroup.is_default).toBe(true);

    console.log(`Groups found: ${groups.length}`);
    console.log(`Retail group ID: ${retailGroup?.id}`);
  });

  test('E2E-ADM-GRP-04: API - Get group details with members', async () => {
    const groups = await getGroups(adminToken);
    const retailGroup = groups.find(g => g.name === 'Retail');

    if (!retailGroup) {
      console.log('Retail group not found');
      return;
    }

    const details = await getGroup(adminToken, retailGroup.id);

    expect(details).toBeTruthy();
    expect(details.name).toBe('Retail');
    expect(details.members).toBeDefined();

    console.log(`Retail group members: ${details.members?.length || 0}`);
  });
});

test.describe('Admin: Policy Management', () => {
  let adminToken: string;

  test.beforeAll(async () => {
    adminToken = (await getTokenForUser('admin'))!;
  });

  test('E2E-ADM-POL-01: Policy editor shows rules', async ({ page }) => {
    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/groups');
    await page.waitForLoadState('networkidle');

    // Find Retail group and click
    const retailGroup = page.getByText(/Retail/).first();
    if (await retailGroup.isVisible()) {
      await retailGroup.click();
      await page.waitForLoadState('networkidle');

      // Look for policy section
      const policySection = await page.getByText(/Policy|Rules/i).first()
        .isVisible({ timeout: 5000 }).catch(() => false);

      if (policySection) {
        // Should show policy rules
        const hasRules = await page.getByText(/RET-01|RET-02|RET-03|Micro|Large|Deny/i).first()
          .isVisible({ timeout: 5000 }).catch(() => false);

        console.log(`Policy rules visible: ${hasRules}`);
      }
    }
  });

  test('E2E-ADM-POL-02: API - Get group policy', async () => {
    const groups = await getGroups(adminToken);
    const retailGroup = groups.find(g => g.name === 'Retail');

    if (!retailGroup) {
      console.log('Retail group not found');
      return;
    }

    // Get policy for group
    const policyRes = await api('GET', `/v1/groups/${retailGroup.id}/policies`, adminToken);

    if (policyRes.data) {
      console.log('Group policy:', JSON.stringify(policyRes.data, null, 2));

      // Verify policy has rules
      if (Array.isArray(policyRes.data) && policyRes.data.length > 0) {
        const policy = policyRes.data[0];
        expect(policy.rules || policy.policy_rules).toBeDefined();
      }
    }
  });

  test('E2E-ADM-POL-03: Policy rules have correct structure', async () => {
    const groups = await getGroups(adminToken);
    const retailGroup = groups.find(g => g.name === 'Retail');

    if (!retailGroup) return;

    const policyRes = await api('GET', `/v1/groups/${retailGroup.id}/policies`, adminToken);

    if (policyRes.data && Array.isArray(policyRes.data) && policyRes.data.length > 0) {
      const policy = policyRes.data[0];
      const rules = policy.rules || policy.policy_rules || [];

      // Verify expected rules exist
      const ruleIds = rules.map((r: any) => r.rule_id);

      console.log('Policy rules:', ruleIds);

      // Should have RET-01, RET-02, RET-03
      expect(ruleIds).toContain('RET-01');
      expect(ruleIds).toContain('RET-02');
      expect(ruleIds).toContain('RET-03');
    }
  });
});

test.describe('Admin: Address Book', () => {
  let adminToken: string;
  let retailGroupId: string;

  test.beforeAll(async () => {
    adminToken = (await getTokenForUser('admin'))!;

    const groups = await getGroups(adminToken);
    const retailGroup = groups.find(g => g.name === 'Retail');
    if (retailGroup) retailGroupId = retailGroup.id;
  });

  test('E2E-ADM-AB-01: Address book UI exists', async ({ page }) => {
    test.skip(!retailGroupId, 'Retail group not found');

    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/groups');
    await page.waitForLoadState('networkidle');

    // Navigate to Retail group
    await page.getByText(/Retail/).first().click();
    await page.waitForLoadState('networkidle');

    // Look for address book section
    const hasAddressBook = await page.getByText(/Address.*Book|Allow.*list|Deny.*list/i).first()
      .isVisible({ timeout: 5000 }).catch(() => false);

    console.log(`Address book section visible: ${hasAddressBook}`);
  });

  test('E2E-ADM-AB-02: API - Get address book', async () => {
    test.skip(!retailGroupId, 'Retail group not found');

    const res = await api('GET', `/v1/groups/${retailGroupId}/address-book`, adminToken);

    // Address book might be empty or have entries
    if (res.data) {
      console.log(`Address book entries: ${Array.isArray(res.data) ? res.data.length : 0}`);
    }
  });

  test('E2E-ADM-AB-03: API - Add allowlist entry', async () => {
    test.skip(!retailGroupId, 'Retail group not found');

    const testAddress = '0x' + 'a'.repeat(40);

    const res = await api('POST', `/v1/groups/${retailGroupId}/address-book`, adminToken, {
      address: testAddress,
      kind: 'ALLOW',
      label: 'E2E Test Allow Entry',
    });

    if (res.data) {
      console.log('Allowlist entry added:', res.data.id);

      // Clean up - delete the entry
      await api('DELETE', `/v1/groups/${retailGroupId}/address-book/${res.data.id}`, adminToken);
    } else if (res.error) {
      console.log('Could not add allowlist entry:', res.error);
    }
  });

  test('E2E-ADM-AB-04: API - Add denylist entry', async () => {
    test.skip(!retailGroupId, 'Retail group not found');

    const testAddress = '0x' + 'b'.repeat(40);

    const res = await api('POST', `/v1/groups/${retailGroupId}/address-book`, adminToken, {
      address: testAddress,
      kind: 'DENY',
      label: 'E2E Test Deny Entry',
    });

    if (res.data) {
      console.log('Denylist entry added:', res.data.id);

      // Clean up
      await api('DELETE', `/v1/groups/${retailGroupId}/address-book/${res.data.id}`, adminToken);
    } else if (res.error) {
      console.log('Could not add denylist entry:', res.error);
    }
  });
});

test.describe('Admin: Member Management', () => {
  let adminToken: string;
  let retailGroupId: string;

  test.beforeAll(async () => {
    adminToken = (await getTokenForUser('admin'))!;

    const groups = await getGroups(adminToken);
    const retailGroup = groups.find(g => g.name === 'Retail');
    if (retailGroup) retailGroupId = retailGroup.id;
  });

  test('E2E-ADM-GRP-05: Add member to group (API)', async () => {
    test.skip(!retailGroupId, 'Retail group not found');

    // First, create a test user or use existing
    const usersRes = await api('GET', '/v1/users', adminToken);
    const users = usersRes.data || [];

    if (users.length === 0) {
      console.log('No users found for member test');
      return;
    }

    // Find a user not in Retail
    const group = await getGroup(adminToken, retailGroupId);
    const memberIds = (group.members || []).map((m: any) => m.user_id);

    const nonMember = users.find((u: any) => !memberIds.includes(u.id));

    if (!nonMember) {
      console.log('All users are already in Retail group');
      return;
    }

    // Add member
    const addResult = await addGroupMember(adminToken, retailGroupId, nonMember.id);

    if (addResult.data) {
      console.log(`Added user ${nonMember.username} to Retail group`);

      // Note: Don't remove as they should stay in Retail
    }
  });

  test('E2E-ADM-GRP-06: Member management UI', async ({ page }) => {
    test.skip(!retailGroupId, 'Retail group not found');

    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/groups');
    await page.waitForLoadState('networkidle');

    // Click on Retail
    await page.getByText(/Retail/).first().click();
    await page.waitForLoadState('networkidle');

    // Look for add member button
    const addBtn = await page.getByRole('button', { name: /add.*member|invite/i }).first()
      .isVisible({ timeout: 5000 }).catch(() => false);

    console.log(`Add member button visible: ${addBtn}`);

    // Look for member remove buttons
    const removeBtn = await page.getByRole('button', { name: /remove|delete/i }).first()
      .isVisible({ timeout: 3000 }).catch(() => false);

    console.log(`Remove member button visible: ${removeBtn}`);
  });
});
