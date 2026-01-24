'use client';

import * as React from 'react';
import { FileJson, ExternalLink, Shield, Copy, Check, ArrowDownLeft } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/badge';
import { DepositTimeline } from './DepositTimeline';
import { depositsApi } from '@/lib/api';
import { formatAddress, formatEth, getExplorerLink } from '@/lib/utils';
import { Deposit, DepositAuditPackage } from '@/types';
import { BitOKReport } from '@/components/kyt/BitOKReport';

interface DepositAuditModalProps {
  deposit: Deposit | null;
  open: boolean;
  onClose: () => void;
}

export function DepositAuditModal({ deposit, open, onClose }: DepositAuditModalProps) {
  const [auditPackage, setAuditPackage] = React.useState<DepositAuditPackage | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState<'timeline' | 'kyt'>('timeline');

  React.useEffect(() => {
    if (open && deposit) {
      loadAuditPackage();
    }
  }, [open, deposit]);

  const loadAuditPackage = async () => {
    if (!deposit) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await depositsApi.getAuditPackage(deposit.id);
      setAuditPackage(response.data);
    } catch (err) {
      console.error('Failed to load audit package:', err);
      setError('Failed to load audit trail. Some data may be incomplete.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleExportJSON = () => {
    if (!deposit) return;

    const exportData = {
      export_version: '1.0',
      export_type: 'DEPOSIT_AUDIT_PACKAGE',
      exported_at: new Date().toISOString(),
      deposit: {
        id: deposit.id,
        wallet_id: deposit.wallet_id,
        tx_hash: deposit.tx_hash,
        from_address: deposit.from_address,
        amount: deposit.amount,
        asset: deposit.asset,
        block_number: deposit.block_number,
        status: deposit.status,
        kyt_result: deposit.kyt_result,
        kyt_case_id: deposit.kyt_case_id,
        detected_at: deposit.detected_at,
        approved_by: deposit.approved_by,
        approved_at: deposit.approved_at,
      },
      kyt_evaluation: auditPackage?.kyt_evaluation,
      admin_decision: auditPackage?.admin_decision,
      audit_events: auditPackage?.audit_events || [],
      package_hash: auditPackage?.package_hash,
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `deposit-audit-${deposit.id.slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopyId = async () => {
    if (!deposit) return;
    await navigator.clipboard.writeText(deposit.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!deposit) return null;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-brand-400" />
              Deposit Audit Package
            </DialogTitle>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleExportJSON}>
                <FileJson className="h-4 w-4 mr-2" />
                Export JSON
              </Button>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto -mx-6 px-6">
          {/* Deposit Summary Card */}
          <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700 mb-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <ArrowDownLeft className="h-5 w-5 text-emerald-400" />
                <span className="text-sm text-surface-500">Deposit ID</span>
                <button
                  onClick={handleCopyId}
                  className="text-surface-400 hover:text-surface-200 transition-colors"
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </button>
              </div>
              <StatusBadge status={deposit.status} />
            </div>

            <div className="font-mono text-xs text-surface-500 mb-4 break-all">
              {deposit.id}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-xs text-surface-500 uppercase tracking-wider">From</span>
                <a
                  href={getExplorerLink('address', deposit.from_address)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block font-mono text-sm text-brand-400 hover:text-brand-300 mt-1 flex items-center gap-1"
                >
                  {formatAddress(deposit.from_address)}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div>
                <span className="text-xs text-surface-500 uppercase tracking-wider">Amount</span>
                <p className="font-mono text-lg text-emerald-400 mt-1">
                  +{formatEth(deposit.amount)} ETH
                </p>
              </div>
              <div className="col-span-2">
                <span className="text-xs text-surface-500 uppercase tracking-wider">TX Hash</span>
                <a
                  href={getExplorerLink('tx', deposit.tx_hash)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block font-mono text-sm text-brand-400 hover:text-brand-300 mt-1 flex items-center gap-1"
                >
                  {deposit.tx_hash}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-4 border-b border-surface-700">
            <button
              onClick={() => setActiveTab('timeline')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'timeline'
                  ? 'text-brand-400 border-b-2 border-brand-400'
                  : 'text-surface-400 hover:text-surface-200'
              }`}
            >
              Audit Timeline
            </button>
            <button
              onClick={() => setActiveTab('kyt')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'kyt'
                  ? 'text-brand-400 border-b-2 border-brand-400'
                  : 'text-surface-400 hover:text-surface-200'
              }`}
            >
              KYT Report
            </button>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-6 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm">
              {error}
            </div>
          )}

          {/* Tab Content */}
          {activeTab === 'timeline' ? (
            <DepositTimeline
              auditPackage={auditPackage}
              deposit={deposit}
              isLoading={isLoading}
              onExport={handleExportJSON}
            />
          ) : (
            <BitOKReport
              deposit={{
                tx_hash: deposit.tx_hash,
                from_address: deposit.from_address,
                amount: deposit.amount,
                wallet_id: deposit.wallet_id,
              }}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex-shrink-0 pt-4 border-t border-surface-700 -mx-6 px-6">
          <div className="flex items-center justify-between text-xs text-surface-500">
            <span>
              {auditPackage?.audit_events?.length || 0} audit events recorded
            </span>
            <span>
              Generated: {new Date().toLocaleString()}
            </span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
