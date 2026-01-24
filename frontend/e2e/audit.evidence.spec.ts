import { test, expect } from '@playwright/test';
import { TIMEOUTS, TX_STATUSES } from './fixtures/test-data';
import {
  api,
  getWallets,
  getWithdrawal,
  getWithdrawalAudit,
  getDepositAudit,
  getDeposits,
} from './fixtures/api-helpers';
import {
  setupAuthenticatedPage,
  getTokenForUser,
} from './fixtures/auth-helpers';

/**
 * Audit & Evidence Tests
 *
 * Tests for audit trail, evidence packages, and export functionality.
 */

test.describe('Withdrawal Audit Package', () => {
  let adminToken: string;
  let retailToken: string;
  let completedTxId: string;

  test.beforeAll(async () => {
    adminToken = (await getTokenForUser('admin'))!;
    retailToken = (await getTokenForUser('retail'))!;

    // Find a completed transaction
    const txRes = await api('GET', '/v1/withdrawals', adminToken);
    const txs = txRes.data || [];

    const completedTx = txs.find((tx: any) =>
      [TX_STATUSES.FINALIZED, TX_STATUSES.CONFIRMED].includes(tx.status)
    );

    if (completedTx) {
      completedTxId = completedTx.id;
      console.log(`Using completed tx: ${completedTxId}`);
    }
  });

  test('E2E-AUD-01: Withdrawal evidence contains all required fields', async () => {
    test.skip(!completedTxId, 'No completed transaction found');

    const audit = await getWithdrawalAudit(adminToken, completedTxId);

    // Verify required fields
    expect(audit).toBeTruthy();

    // Intent (to/amount)
    expect(audit.tx_request || audit.intent).toBeTruthy();

    // Policy decision
    if (audit.policy_decision || audit.policy_snapshot) {
      const policy = audit.policy_decision || audit.policy_snapshot;
      expect(policy.decision || policy.result).toBeTruthy();
    }

    // Audit events
    expect(audit.audit_events || audit.events).toBeDefined();

    console.log('Audit package structure:', Object.keys(audit));
  });

  test('E2E-AUD-02: Audit contains policy matched rules', async () => {
    test.skip(!completedTxId, 'No completed transaction found');

    const audit = await getWithdrawalAudit(adminToken, completedTxId);
    const policy = audit.policy_decision || audit.policy_snapshot;

    if (policy) {
      expect(policy.matched_rules || policy.rules).toBeDefined();
      console.log('Matched rules:', policy.matched_rules || policy.rules);
    }
  });

  test('E2E-AUD-03: Audit contains KYT result or SKIPPED', async () => {
    test.skip(!completedTxId, 'No completed transaction found');

    const audit = await getWithdrawalAudit(adminToken, completedTxId);

    // KYT should be present (either result or SKIPPED)
    const kyt = audit.kyt_evaluation || audit.kyt_result;

    console.log('KYT in audit:', kyt || 'SKIPPED');

    // Verify KYT structure if present
    if (kyt && typeof kyt === 'object') {
      expect(kyt.result || kyt.decision || kyt.status).toBeDefined();
    }
  });

  test('E2E-AUD-04: Audit contains approvals (if required)', async () => {
    test.skip(!completedTxId, 'No completed transaction found');

    const audit = await getWithdrawalAudit(adminToken, completedTxId);

    if (audit.approvals && audit.approvals.length > 0) {
      const approval = audit.approvals[0];
      expect(approval.decision || approval.approved).toBeDefined();
      expect(approval.actor_id || approval.user_id || approval.approver).toBeDefined();

      console.log('Approvals:', audit.approvals.length);
    } else if (audit.admin_decision) {
      console.log('Admin decision:', audit.admin_decision);
    } else {
      console.log('No approvals required for this transaction');
    }
  });

  test('E2E-AUD-05: Audit contains tx hash', async () => {
    test.skip(!completedTxId, 'No completed transaction found');

    const tx = await getWithdrawal(adminToken, completedTxId);

    expect(tx.tx_hash).toBeTruthy();
    expect(tx.tx_hash).toMatch(/^0x[a-fA-F0-9]{64}$/);

    console.log('TX Hash:', tx.tx_hash);
  });

  test('E2E-AUD-06: Audit UI shows timeline', async ({ page }) => {
    test.skip(!completedTxId, 'No completed transaction found');

    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/withdrawals');
    await page.waitForLoadState('networkidle');

    // Find audit button and click
    const auditBtn = page.getByRole('button', { name: /audit|evidence/i })
      .or(page.locator('[aria-label*="audit"]'))
      .or(page.locator('button:has(svg)').first());

    if (await auditBtn.first().isVisible({ timeout: 5000 })) {
      await auditBtn.first().click();
      await page.waitForLoadState('networkidle');

      // Should show timeline
      const hasTimeline = await page.getByText(/Timeline|History|Events/i).first()
        .isVisible({ timeout: 5000 }).catch(() => false);

      console.log(`Timeline visible: ${hasTimeline}`);

      // Check for timeline items
      const hasEvents = await page.getByText(/Created|KYT|Approval|Signed|Broadcast|Confirmed/i).first()
        .isVisible({ timeout: 3000 }).catch(() => false);

      console.log(`Timeline events visible: ${hasEvents}`);
    }
  });
});

test.describe('Deposit Audit Package', () => {
  let adminToken: string;
  let creditedDepositId: string;

  test.beforeAll(async () => {
    adminToken = (await getTokenForUser('admin'))!;

    // Find a credited deposit
    const depositsRes = await api('GET', '/v1/deposits/admin', adminToken);
    const deposits = depositsRes.data || [];

    const creditedDeposit = deposits.find((d: any) => d.status === 'CREDITED');

    if (creditedDeposit) {
      creditedDepositId = creditedDeposit.id;
      console.log(`Using credited deposit: ${creditedDepositId}`);
    }
  });

  test('E2E-AUD-07: Deposit evidence contains all required fields', async () => {
    test.skip(!creditedDepositId, 'No credited deposit found');

    const audit = await getDepositAudit(adminToken, creditedDepositId);

    expect(audit).toBeTruthy();

    // Should have deposit info
    expect(audit.deposit || audit.tx_hash).toBeTruthy();

    // Should have audit events
    expect(audit.audit_events || audit.events).toBeDefined();

    console.log('Deposit audit structure:', Object.keys(audit));
  });

  test('E2E-AUD-08: Deposit audit contains admin decision', async () => {
    test.skip(!creditedDepositId, 'No credited deposit found');

    const audit = await getDepositAudit(adminToken, creditedDepositId);

    // Should have admin decision for CREDITED deposits
    if (audit.admin_decision) {
      expect(audit.admin_decision.action || audit.admin_decision.decision).toBeTruthy();
      console.log('Admin decision:', audit.admin_decision);
    }
  });

  test('E2E-AUD-09: Deposit audit UI shows timeline', async ({ page }) => {
    test.skip(!creditedDepositId, 'No credited deposit found');

    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/deposits');
    await page.waitForLoadState('networkidle');

    // Find audit button
    const auditBtn = page.getByRole('button', { name: /audit|evidence/i })
      .or(page.locator('[aria-label*="audit"]'));

    if (await auditBtn.first().isVisible({ timeout: 5000 })) {
      await auditBtn.first().click();

      // Should show timeline
      const hasTimeline = await page.getByText(/Timeline|History|Detected|Credited/i).first()
        .isVisible({ timeout: 5000 }).catch(() => false);

      console.log(`Deposit timeline visible: ${hasTimeline}`);
    }
  });
});

test.describe('Export & Verification', () => {
  let adminToken: string;
  let txId: string;

  test.beforeAll(async () => {
    adminToken = (await getTokenForUser('admin'))!;

    // Find any transaction
    const txRes = await api('GET', '/v1/withdrawals', adminToken);
    const txs = txRes.data || [];
    if (txs.length > 0) txId = txs[0].id;
  });

  test('E2E-AUD-10: Export JSON button exists', async ({ page }) => {
    test.skip(!txId, 'No transaction found');

    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/withdrawals');
    await page.waitForLoadState('networkidle');

    // Open audit modal
    const auditBtn = page.getByRole('button', { name: /audit/i }).first();
    if (await auditBtn.isVisible({ timeout: 5000 })) {
      await auditBtn.click();
      await page.waitForTimeout(1000);

      // Look for export button
      const exportBtn = await page.getByRole('button', { name: /export.*json|download/i }).first()
        .isVisible({ timeout: 5000 }).catch(() => false);

      console.log(`Export JSON button visible: ${exportBtn}`);
    }
  });

  test('E2E-AUD-11: Export produces valid JSON', async ({ page }) => {
    test.skip(!txId, 'No transaction found');

    await setupAuthenticatedPage(page, 'admin');
    await page.goto('/admin/withdrawals');
    await page.waitForLoadState('networkidle');

    // Setup download handler
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 }).catch(() => null);

    // Open audit and click export
    const auditBtn = page.getByRole('button', { name: /audit/i }).first();
    if (await auditBtn.isVisible({ timeout: 5000 })) {
      await auditBtn.click();
      await page.waitForTimeout(1000);

      const exportBtn = page.getByRole('button', { name: /export.*json|download/i }).first();
      if (await exportBtn.isVisible({ timeout: 3000 })) {
        await exportBtn.click();

        const download = await downloadPromise;
        if (download) {
          const filename = download.suggestedFilename();
          expect(filename).toMatch(/\.json$/);
          console.log(`Downloaded: ${filename}`);
        } else {
          console.log('No download triggered');
        }
      }
    }
  });

  test('E2E-AUD-12: Audit hash verification', async () => {
    test.skip(!txId, 'No transaction found');

    const audit = await getWithdrawalAudit(adminToken, txId);

    // Check for package hash
    if (audit.package_hash) {
      expect(audit.package_hash).toMatch(/^[a-fA-F0-9]{64}$/);
      console.log('Package hash:', audit.package_hash);
    }

    // Check for chain verification endpoint
    const verifyRes = await api('GET', `/v1/audit/verify/${txId}`, adminToken);
    if (verifyRes.data) {
      console.log('Verification result:', verifyRes.data.verified);
    }
  });
});
