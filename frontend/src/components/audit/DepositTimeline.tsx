'use client';

import * as React from 'react';
import {
  ArrowDownLeft,
  Shield,
  UserCheck,
  CheckCircle,
  XCircle,
  Clock,
  Download,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Search,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/badge';
import { formatAddress, formatEth, getExplorerLink } from '@/lib/utils';
import { Deposit, DepositAuditPackage, AuditEvent } from '@/types';

interface TimelineStep {
  id: string;
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  status: 'completed' | 'current' | 'pending' | 'failed' | 'skipped';
  timestamp?: string;
  details?: React.ReactNode;
  expandable?: boolean;
}

interface DepositTimelineProps {
  auditPackage: DepositAuditPackage | null;
  deposit: Deposit;
  isLoading?: boolean;
  onExport?: () => void;
}

export function DepositTimeline({
  auditPackage,
  deposit,
  isLoading = false,
  onExport,
}: DepositTimelineProps) {
  const [expandedSteps, setExpandedSteps] = React.useState<Set<string>>(new Set(['detected', 'kyt', 'decision']));

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  };

  // Build timeline steps
  const buildSteps = (): TimelineStep[] => {
    const steps: TimelineStep[] = [];
    const events = auditPackage?.audit_events || [];

    // 1. Deposit Detected
    const detectedEvent = events.find((e) => e.event_type === 'DEPOSIT_DETECTED');

    steps.push({
      id: 'detected',
      title: 'Deposit Detected',
      subtitle: `${formatEth(deposit.amount)} ETH from ${formatAddress(deposit.from_address)}`,
      icon: <ArrowDownLeft className="h-5 w-5" />,
      status: 'completed',
      timestamp: deposit.detected_at,
      expandable: true,
      details: (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-surface-500">Transaction Hash</span>
            <a
              href={getExplorerLink('tx', deposit.tx_hash)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-brand-400 hover:text-brand-300 flex items-center gap-1"
            >
              {formatAddress(deposit.tx_hash, 10)}
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">From Address</span>
            <a
              href={getExplorerLink('address', deposit.from_address)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-brand-400 hover:text-brand-300 flex items-center gap-1"
            >
              {formatAddress(deposit.from_address)}
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">Amount</span>
            <span className="font-mono text-surface-300">{formatEth(deposit.amount)} ETH</span>
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">Block Number</span>
            <span className="font-mono text-surface-300">{deposit.block_number || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">To Wallet</span>
            <span className="font-mono text-surface-300">{formatAddress(deposit.wallet_id)}</span>
          </div>
        </div>
      ),
    });

    // 2. KYT Screening
    const kytEvent = events.find((e) => e.event_type === 'DEPOSIT_KYT_EVALUATED');
    const kytResult = deposit.kyt_result;

    let kytStatus: TimelineStep['status'] = 'pending';
    if (kytResult) {
      kytStatus = kytResult === 'ALLOW' ? 'completed' : kytResult === 'BLOCK' ? 'failed' : 'current';
    }

    steps.push({
      id: 'kyt',
      title: 'KYT Screening',
      subtitle: kytResult
        ? `Result: ${kytResult}`
        : 'Pending...',
      icon: <Shield className="h-5 w-5" />,
      status: kytStatus,
      timestamp: kytEvent?.timestamp,
      expandable: true,
      details: (
        <div className="space-y-2 text-sm">
          {kytResult ? (
            <>
              <div className="flex justify-between items-center">
                <span className="text-surface-500">Decision</span>
                <StatusBadge status={kytResult} />
              </div>
              {auditPackage?.kyt_evaluation && (
                <>
                  {auditPackage.kyt_evaluation.risk_score !== undefined && (
                    <div className="flex justify-between">
                      <span className="text-surface-500">Risk Score</span>
                      <span className={`font-mono ${
                        auditPackage.kyt_evaluation.risk_score < 30 ? 'text-emerald-400' :
                        auditPackage.kyt_evaluation.risk_score < 70 ? 'text-amber-400' : 'text-red-400'
                      }`}>
                        {auditPackage.kyt_evaluation.risk_score}/100
                      </span>
                    </div>
                  )}
                  {auditPackage.kyt_evaluation.provider && (
                    <div className="flex justify-between">
                      <span className="text-surface-500">Provider</span>
                      <span className="text-surface-300">{auditPackage.kyt_evaluation.provider}</span>
                    </div>
                  )}
                  {auditPackage.kyt_evaluation.counterparty_type && (
                    <div className="flex justify-between">
                      <span className="text-surface-500">Counterparty Type</span>
                      <span className="text-surface-300">{auditPackage.kyt_evaluation.counterparty_type}</span>
                    </div>
                  )}
                </>
              )}
              {deposit.kyt_case_id && (
                <div className="flex justify-between">
                  <span className="text-surface-500">Case ID</span>
                  <span className="font-mono text-surface-300">{formatAddress(deposit.kyt_case_id)}</span>
                </div>
              )}
              {kytResult === 'REVIEW' && (
                <div className="mt-2 p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
                  <AlertTriangle className="h-3 w-3 inline mr-1" />
                  This deposit was flagged for manual review by compliance
                </div>
              )}
              {kytResult === 'BLOCK' && (
                <div className="mt-2 p-2 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                  <XCircle className="h-3 w-3 inline mr-1" />
                  This deposit was blocked due to high risk indicators
                </div>
              )}
            </>
          ) : (
            <div className="p-3 rounded bg-surface-800/50 text-surface-400">
              Awaiting KYT screening...
            </div>
          )}
        </div>
      ),
    });

    // 3. Admin Review/Decision
    const approvedEvent = events.find((e) => e.event_type === 'DEPOSIT_APPROVED');
    const rejectedEvent = events.find((e) => e.event_type === 'DEPOSIT_REJECTED');
    const adminDecision = auditPackage?.admin_decision;

    let decisionStatus: TimelineStep['status'] = 'pending';
    let decisionTitle = 'Admin Review';
    let decisionSubtitle = 'Pending approval...';

    if (deposit.status === 'CREDITED' || adminDecision?.decision === 'APPROVED') {
      decisionStatus = 'completed';
      decisionTitle = 'Approved';
      decisionSubtitle = `By ${formatAddress(deposit.approved_by || adminDecision?.decided_by || '')}`;
    } else if (deposit.status === 'REJECTED' || adminDecision?.decision === 'REJECTED') {
      decisionStatus = 'failed';
      decisionTitle = 'Rejected';
      decisionSubtitle = adminDecision?.reason || 'Deposit rejected by admin';
    } else if (deposit.status === 'PENDING_ADMIN') {
      decisionStatus = 'current';
    }

    steps.push({
      id: 'decision',
      title: decisionTitle,
      subtitle: decisionSubtitle,
      icon: <UserCheck className="h-5 w-5" />,
      status: decisionStatus,
      timestamp: deposit.approved_at || adminDecision?.decided_at,
      expandable: true,
      details: (
        <div className="space-y-2 text-sm">
          {adminDecision ? (
            <>
              <div className="flex justify-between items-center">
                <span className="text-surface-500">Decision</span>
                <StatusBadge status={adminDecision.decision} />
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Decided By</span>
                <span className="font-mono text-surface-300">{formatAddress(adminDecision.decided_by)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Decided At</span>
                <span className="text-surface-300">{new Date(adminDecision.decided_at).toLocaleString()}</span>
              </div>
              {adminDecision.reason && (
                <div className="mt-2 p-2 rounded bg-surface-800/50">
                  <span className="text-surface-500 text-xs">Reason:</span>
                  <p className="text-surface-300 mt-1">{adminDecision.reason}</p>
                </div>
              )}
            </>
          ) : deposit.status === 'CREDITED' ? (
            <>
              <div className="flex justify-between items-center">
                <span className="text-surface-500">Decision</span>
                <StatusBadge status="APPROVED" />
              </div>
              {deposit.approved_by && (
                <div className="flex justify-between">
                  <span className="text-surface-500">Approved By</span>
                  <span className="font-mono text-surface-300">{formatAddress(deposit.approved_by)}</span>
                </div>
              )}
              {deposit.approved_at && (
                <div className="flex justify-between">
                  <span className="text-surface-500">Approved At</span>
                  <span className="text-surface-300">{new Date(deposit.approved_at).toLocaleString()}</span>
                </div>
              )}
            </>
          ) : (
            <div className="p-3 rounded bg-surface-800/50 text-surface-400">
              <Clock className="h-4 w-4 inline mr-2" />
              Awaiting admin review and approval...
            </div>
          )}
        </div>
      ),
    });

    // 4. Credited (Final Status)
    let creditedStatus: TimelineStep['status'] = 'pending';
    if (deposit.status === 'CREDITED') {
      creditedStatus = 'completed';
    } else if (deposit.status === 'REJECTED') {
      creditedStatus = 'failed';
    }

    steps.push({
      id: 'credited',
      title: deposit.status === 'REJECTED' ? 'Not Credited' : 'Balance Credited',
      subtitle: deposit.status === 'CREDITED'
        ? `${formatEth(deposit.amount)} ETH added to wallet balance`
        : deposit.status === 'REJECTED'
        ? 'Deposit was rejected'
        : 'Pending...',
      icon: deposit.status === 'REJECTED' ? <XCircle className="h-5 w-5" /> : <CheckCircle className="h-5 w-5" />,
      status: creditedStatus,
      expandable: creditedStatus !== 'pending',
      details: creditedStatus !== 'pending' && (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between items-center">
            <span className="text-surface-500">Final Status</span>
            <StatusBadge status={deposit.status} />
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">Amount</span>
            <span className="font-mono text-surface-300">{formatEth(deposit.amount)} ETH</span>
          </div>
          {deposit.status === 'CREDITED' && (
            <div className="mt-2 p-2 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
              <CheckCircle className="h-3 w-3 inline mr-1" />
              Funds have been credited to the user's available balance
            </div>
          )}
        </div>
      ),
    });

    return steps;
  };

  const steps = buildSteps();

  const getStatusColor = (status: TimelineStep['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-emerald-500 text-white';
      case 'current':
        return 'bg-brand-500 text-white animate-pulse';
      case 'failed':
        return 'bg-red-500 text-white';
      case 'skipped':
        return 'bg-surface-600 text-surface-400';
      default:
        return 'bg-surface-700 text-surface-500';
    }
  };

  const getLineColor = (status: TimelineStep['status']) => {
    switch (status) {
      case 'completed':
        return 'bg-emerald-500';
      case 'failed':
        return 'bg-red-500';
      case 'skipped':
        return 'bg-surface-600';
      default:
        return 'bg-surface-700';
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-brand-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Export */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-surface-200">Deposit Audit Trail</h3>
        {onExport && (
          <Button variant="outline" size="sm" onClick={onExport}>
            <Download className="h-4 w-4 mr-2" />
            Export Audit Package
          </Button>
        )}
      </div>

      {/* Timeline */}
      <div className="relative">
        {steps.map((step, index) => {
          const isExpanded = expandedSteps.has(step.id);
          const isLast = index === steps.length - 1;

          return (
            <div key={step.id} className="relative">
              {/* Connector Line */}
              {!isLast && (
                <div
                  className={`absolute left-5 top-10 w-0.5 h-full -translate-x-1/2 ${getLineColor(step.status)}`}
                />
              )}

              {/* Step */}
              <div className="relative flex gap-4 pb-6">
                {/* Icon */}
                <div
                  className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${getStatusColor(
                    step.status
                  )}`}
                >
                  {step.icon}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div
                    className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                      step.expandable
                        ? 'cursor-pointer hover:bg-surface-800/50 border-surface-700'
                        : 'border-transparent'
                    }`}
                    onClick={() => step.expandable && toggleStep(step.id)}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium text-surface-200">{step.title}</h4>
                        {step.status === 'skipped' && (
                          <span className="text-xs px-2 py-0.5 rounded bg-surface-700 text-surface-400">
                            SKIPPED
                          </span>
                        )}
                      </div>
                      {step.subtitle && (
                        <p className="text-sm text-surface-500 mt-0.5">{step.subtitle}</p>
                      )}
                      {step.timestamp && (
                        <p className="text-xs text-surface-600 mt-1">
                          {new Date(step.timestamp).toLocaleString()}
                        </p>
                      )}
                    </div>

                    {step.expandable && (
                      <div className="text-surface-500">
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </div>
                    )}
                  </div>

                  {/* Expanded Details */}
                  {step.expandable && isExpanded && step.details && (
                    <div className="mt-2 ml-3 p-4 rounded-lg bg-surface-800/50 border border-surface-700">
                      {step.details}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Hash Chain Verification */}
      {auditPackage && (
        <div className="mt-6 p-4 rounded-lg bg-surface-800/30 border border-surface-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-brand-400" />
              <span className="text-sm text-surface-400">Audit Package Hash</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-emerald-400" />
              <span className="text-xs text-emerald-400">Verified</span>
            </div>
          </div>
          <p className="mt-2 font-mono text-xs text-surface-500 break-all">
            {auditPackage.package_hash}
          </p>
        </div>
      )}
    </div>
  );
}
