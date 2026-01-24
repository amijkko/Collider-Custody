'use client';

import * as React from 'react';
import { Download, FileJson, FileText, X, ExternalLink, Shield, Copy, Check } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/badge';
import { TransactionTimeline } from './TransactionTimeline';
import { auditApi } from '@/lib/api';
import { formatAddress, formatEth, getExplorerLink } from '@/lib/utils';
import { WithdrawRequest, AuditPackage } from '@/types';

interface TransactionAuditModalProps {
  txRequest: WithdrawRequest | null;
  open: boolean;
  onClose: () => void;
}

export function TransactionAuditModal({ txRequest, open, onClose }: TransactionAuditModalProps) {
  const [auditPackage, setAuditPackage] = React.useState<AuditPackage | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (open && txRequest) {
      loadAuditPackage();
    }
  }, [open, txRequest]);

  const loadAuditPackage = async () => {
    if (!txRequest) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await auditApi.getPackage(txRequest.id);
      setAuditPackage(response.data);
    } catch (err) {
      console.error('Failed to load audit package:', err);
      setError('Failed to load audit trail. Some data may be incomplete.');
      // Still show what we have from txRequest
    } finally {
      setIsLoading(false);
    }
  };

  const handleExportJSON = () => {
    if (!txRequest) return;

    const exportData = {
      export_version: '1.0',
      exported_at: new Date().toISOString(),
      tx_request: {
        id: txRequest.id,
        wallet_id: txRequest.wallet_id,
        to_address: txRequest.to_address,
        amount: txRequest.amount,
        asset: txRequest.asset,
        status: txRequest.status,
        tx_hash: txRequest.tx_hash,
        block_number: txRequest.block_number,
        confirmations: txRequest.confirmations,
        created_at: txRequest.created_at,
        created_by: txRequest.created_by,
      },
      policy_evaluation: txRequest.policy_result || auditPackage?.policy_evaluation,
      kyt_evaluation: txRequest.kyt_result
        ? { result: txRequest.kyt_result, ...auditPackage?.kyt_evaluation }
        : auditPackage?.kyt_evaluation,
      approvals: txRequest.approvals || auditPackage?.approvals || [],
      signing: auditPackage?.signing,
      broadcast: auditPackage?.broadcast,
      confirmations: auditPackage?.confirmations,
      audit_events: auditPackage?.audit_events || [],
      verification: auditPackage?.verification,
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-package-${txRequest.id.slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopyId = async () => {
    if (!txRequest) return;
    await navigator.clipboard.writeText(txRequest.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!txRequest) return null;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-brand-400" />
              Transaction Audit Package
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
          {/* Transaction Summary Card */}
          <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700 mb-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-surface-500">Transaction ID</span>
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
              <StatusBadge status={txRequest.status} />
            </div>

            <div className="font-mono text-xs text-surface-500 mb-4 break-all">
              {txRequest.id}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-xs text-surface-500 uppercase tracking-wider">Destination</span>
                <a
                  href={getExplorerLink('address', txRequest.to_address)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block font-mono text-sm text-brand-400 hover:text-brand-300 mt-1 flex items-center gap-1"
                >
                  {formatAddress(txRequest.to_address)}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div>
                <span className="text-xs text-surface-500 uppercase tracking-wider">Amount</span>
                <p className="font-mono text-lg text-surface-200 mt-1">
                  {formatEth(txRequest.amount)} ETH
                </p>
              </div>
              {txRequest.tx_hash && (
                <div className="col-span-2">
                  <span className="text-xs text-surface-500 uppercase tracking-wider">TX Hash</span>
                  <a
                    href={getExplorerLink('tx', txRequest.tx_hash)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block font-mono text-sm text-brand-400 hover:text-brand-300 mt-1 flex items-center gap-1"
                  >
                    {txRequest.tx_hash}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-6 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm">
              {error}
            </div>
          )}

          {/* Timeline */}
          <TransactionTimeline
            auditPackage={auditPackage}
            txRequest={txRequest}
            isLoading={isLoading}
            onExport={handleExportJSON}
          />
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
