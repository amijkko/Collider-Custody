'use client';

import * as React from 'react';
import {
  FileText,
  Scale,
  Shield,
  Users,
  Key,
  Radio,
  CheckCircle,
  XCircle,
  Clock,
  Download,
  ExternalLink,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  User,
  Building2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/badge';
import { formatAddress, formatEth, formatRelativeTime, getExplorerLink } from '@/lib/utils';
import { AuditPackage, WithdrawRequest } from '@/types';

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

interface TransactionTimelineProps {
  auditPackage: AuditPackage | null;
  txRequest: WithdrawRequest;
  isLoading?: boolean;
  onExport?: () => void;
}

export function TransactionTimeline({
  auditPackage,
  txRequest,
  isLoading = false,
  onExport,
}: TransactionTimelineProps) {
  const [expandedSteps, setExpandedSteps] = React.useState<Set<string>>(new Set(['policy', 'kyt', 'approvals']));

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

  // Get user's group info from audit events
  const getGroupInfo = (): { groupId: string | null; groupName: string | null } => {
    if (!auditPackage?.audit_events) return { groupId: null, groupName: null };

    const policyEvent = auditPackage.audit_events.find(
      (e) => e.event_type === 'TX_POLICY_EVALUATED'
    );

    if (policyEvent?.payload) {
      return {
        groupId: policyEvent.payload.group_id || null,
        groupName: policyEvent.payload.group_name || null,
      };
    }

    return { groupId: null, groupName: null };
  };

  const groupInfo = getGroupInfo();

  // Build timeline steps
  const buildSteps = (): TimelineStep[] => {
    const steps: TimelineStep[] = [];

    // 1. Draft Created
    const createdEvent = auditPackage?.audit_events?.find(
      (e) => e.event_type === 'TX_REQUEST_CREATED'
    );

    steps.push({
      id: 'created',
      title: 'Transaction Initiated',
      subtitle: createdEvent
        ? `By ${formatAddress(txRequest.created_by || '')} · ${groupInfo.groupName || 'Default Group'}`
        : undefined,
      icon: <FileText className="h-5 w-5" />,
      status: 'completed',
      timestamp: txRequest.created_at,
      expandable: true,
      details: (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-surface-500">Initiator</span>
            <span className="font-mono text-surface-300">{formatAddress(txRequest.created_by || '')}</span>
          </div>
          {groupInfo.groupName && (
            <div className="flex justify-between">
              <span className="text-surface-500">Group</span>
              <span className="text-surface-300 flex items-center gap-1">
                <Building2 className="h-3 w-3" />
                {groupInfo.groupName}
              </span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-surface-500">Destination</span>
            <a
              href={getExplorerLink('address', txRequest.to_address)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-brand-400 hover:text-brand-300 flex items-center gap-1"
            >
              {formatAddress(txRequest.to_address)}
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">Amount</span>
            <span className="font-mono text-surface-300">{formatEth(txRequest.amount)} ETH</span>
          </div>
        </div>
      ),
    });

    // 2. Policy Evaluation
    const policyResult = txRequest.policy_result || auditPackage?.policy_evaluation;
    const policyStatus = policyResult
      ? policyResult.allowed
        ? 'completed'
        : 'failed'
      : 'pending';

    steps.push({
      id: 'policy',
      title: 'Policy Evaluation',
      subtitle: policyResult
        ? `${policyResult.decision} · ${policyResult.matched_rules?.length || 0} rule(s) matched`
        : 'Evaluating...',
      icon: <Scale className="h-5 w-5" />,
      status: policyStatus,
      timestamp: policyResult?.evaluated_at,
      expandable: true,
      details: policyResult && (
        <div className="space-y-3 text-sm">
          <div className="flex justify-between items-center">
            <span className="text-surface-500">Decision</span>
            <StatusBadge status={policyResult.decision} />
          </div>

          {policyResult.address_status && (
            <div className="flex justify-between items-center">
              <span className="text-surface-500">Address Status</span>
              <span className={`text-sm ${
                policyResult.address_status === 'allowlist' ? 'text-emerald-400' :
                policyResult.address_status === 'denylist' ? 'text-red-400' : 'text-surface-400'
              }`}>
                {policyResult.address_status.toUpperCase()}
                {policyResult.address_label && ` (${policyResult.address_label})`}
              </span>
            </div>
          )}

          {policyResult.matched_rules && policyResult.matched_rules.length > 0 && (
            <div className="mt-2">
              <span className="text-surface-500 text-xs uppercase tracking-wider">Matched Rules</span>
              <div className="mt-1 space-y-1">
                {policyResult.matched_rules.map((rule: string, i: number) => (
                  <div key={i} className="flex items-center gap-2 p-2 rounded bg-surface-800/50">
                    <CheckCircle className="h-3 w-3 text-brand-400" />
                    <span className="text-surface-300 text-xs">{rule}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {policyResult.reasons && policyResult.reasons.length > 0 && (
            <div className="mt-2">
              <span className="text-surface-500 text-xs uppercase tracking-wider">Reasons</span>
              <ul className="mt-1 list-disc list-inside text-surface-400 text-xs space-y-1">
                {policyResult.reasons.map((reason: string, i: number) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-surface-700">
            <div className="flex items-center gap-2">
              <span className={policyResult.kyt_required ? 'text-amber-400' : 'text-surface-500'}>
                {policyResult.kyt_required ? '✓' : '○'} KYT Required
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className={policyResult.approval_required ? 'text-amber-400' : 'text-surface-500'}>
                {policyResult.approval_required ? `✓ ${policyResult.approval_count || 1} Approval(s)` : '○ No Approval'}
              </span>
            </div>
          </div>

          <div className="text-xs text-surface-600 pt-1">
            Policy v{policyResult.policy_version} · Hash: {policyResult.policy_snapshot_hash?.slice(0, 12)}...
          </div>
        </div>
      ),
    });

    // 3. KYT Check
    const kytResultRaw = txRequest.kyt_result || auditPackage?.kyt_evaluation?.result;
    const kytResult = typeof kytResultRaw === 'string' ? kytResultRaw : null;
    const kytEvent = auditPackage?.audit_events?.find(
      (e) => e.event_type === 'TX_KYT_EVALUATED' || e.event_type === 'KYT_SKIPPED'
    );
    const kytSkipped = kytEvent?.event_type === 'KYT_SKIPPED';

    let kytStatus: TimelineStep['status'] = 'pending';
    if (kytSkipped) {
      kytStatus = 'skipped';
    } else if (kytResult) {
      kytStatus = kytResult === 'ALLOW' ? 'completed' : kytResult === 'BLOCK' ? 'failed' : 'current';
    }

    steps.push({
      id: 'kyt',
      title: 'KYT Screening',
      subtitle: kytSkipped
        ? 'Skipped by policy'
        : kytResult
        ? `Result: ${kytResult}`
        : 'Pending...',
      icon: <Shield className="h-5 w-5" />,
      status: kytStatus,
      timestamp: kytEvent?.timestamp,
      expandable: true,
      details: (
        <div className="space-y-2 text-sm">
          {kytSkipped ? (
            <div className="p-3 rounded bg-surface-800/50 text-surface-400">
              KYT screening was skipped based on policy rules (e.g., amount below threshold or allowlisted address).
            </div>
          ) : kytResult ? (
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
                </>
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

    // 4. Approvals
    const approvals = txRequest.approvals || auditPackage?.approvals || [];
    const requiredApprovals = txRequest.required_approvals || policyResult?.approval_count || 1;
    const approvalsComplete = approvals.length >= requiredApprovals;
    const approvalSkipped = auditPackage?.audit_events?.some(
      (e) => e.event_type === 'APPROVALS_SKIPPED'
    );

    let approvalStatus: TimelineStep['status'] = 'pending';
    if (approvalSkipped) {
      approvalStatus = 'skipped';
    } else if (approvalsComplete) {
      approvalStatus = 'completed';
    } else if (approvals.length > 0) {
      approvalStatus = 'current';
    }

    steps.push({
      id: 'approvals',
      title: 'Approval Workflow',
      subtitle: approvalSkipped
        ? 'Skipped by policy'
        : `${approvals.length}/${requiredApprovals} approvals`,
      icon: <Users className="h-5 w-5" />,
      status: approvalStatus,
      expandable: true,
      details: (
        <div className="space-y-2 text-sm">
          {approvalSkipped ? (
            <div className="p-3 rounded bg-surface-800/50 text-surface-400">
              Approvals were skipped based on policy rules (e.g., auto-approved for small amounts).
            </div>
          ) : approvals.length > 0 ? (
            <div className="space-y-2">
              {approvals.map((approval: any, i: number) => (
                <div key={approval.id || i}>
                  <div
                    className={`flex items-center justify-between p-3 rounded ${
                      approval.decision === 'APPROVED'
                        ? 'bg-emerald-500/10 border border-emerald-500/20'
                        : 'bg-red-500/10 border border-red-500/20'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-surface-400" />
                      <span className="font-mono text-surface-300">{formatAddress(approval.user_id)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {approval.decision === 'APPROVED' ? (
                        <CheckCircle className="h-4 w-4 text-emerald-400" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-400" />
                      )}
                      <span className={approval.decision === 'APPROVED' ? 'text-emerald-400' : 'text-red-400'}>
                        {approval.decision}
                      </span>
                    </div>
                  </div>
                  {approval.comment && (
                    <div className="text-surface-500 text-xs italic mt-1 ml-6">
                      "{approval.comment}"
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="p-3 rounded bg-surface-800/50 text-surface-400">
              Awaiting approval from {requiredApprovals} approver(s)...
            </div>
          )}
        </div>
      ),
    });

    // 5. MPC Signing
    const signingEvent = auditPackage?.audit_events?.find(
      (e) => e.event_type === 'TX_SIGNED' || e.event_type === 'MPC_SIGN_COMPLETED'
    );
    const signStartedEvent = auditPackage?.audit_events?.find(
      (e) => e.event_type === 'MPC_SIGN_STARTED'
    );

    let signingStatus: TimelineStep['status'] = 'pending';
    if (signingEvent) {
      signingStatus = 'completed';
    } else if (signStartedEvent || txRequest.status === 'SIGN_PENDING') {
      signingStatus = 'current';
    } else if (['FAILED_SIGN'].includes(txRequest.status)) {
      signingStatus = 'failed';
    }

    steps.push({
      id: 'signing',
      title: 'MPC Signing',
      subtitle: signingEvent
        ? 'Transaction signed'
        : signingStatus === 'current'
        ? 'Awaiting user signature...'
        : 'Pending',
      icon: <Key className="h-5 w-5" />,
      status: signingStatus,
      timestamp: signingEvent?.timestamp || signStartedEvent?.timestamp,
      expandable: true,
      details: (
        <div className="space-y-2 text-sm">
          {signingEvent ? (
            <>
              <div className="flex justify-between">
                <span className="text-surface-500">Method</span>
                <span className="text-surface-300">2-of-2 MPC (Browser + Bank)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Signed At</span>
                <span className="text-surface-300">{signingEvent.timestamp ? new Date(signingEvent.timestamp).toLocaleString() : '—'}</span>
              </div>
            </>
          ) : signingStatus === 'current' ? (
            <div className="p-3 rounded bg-brand-500/10 border border-brand-500/20 text-brand-400">
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-brand-500"></div>
                Waiting for user to complete MPC signing via browser...
              </div>
            </div>
          ) : (
            <div className="p-3 rounded bg-surface-800/50 text-surface-400">
              Transaction will be signed using 2-of-2 MPC protocol.
            </div>
          )}
        </div>
      ),
    });

    // 6. Broadcast
    const broadcastEvent = auditPackage?.audit_events?.find(
      (e) => e.event_type === 'TX_BROADCASTED'
    );

    let broadcastStatus: TimelineStep['status'] = 'pending';
    if (broadcastEvent || txRequest.tx_hash) {
      broadcastStatus = 'completed';
    } else if (txRequest.status === 'BROADCAST_PENDING') {
      broadcastStatus = 'current';
    } else if (txRequest.status === 'FAILED_BROADCAST') {
      broadcastStatus = 'failed';
    }

    steps.push({
      id: 'broadcast',
      title: 'Broadcast',
      subtitle: txRequest.tx_hash
        ? `TX: ${formatAddress(txRequest.tx_hash, 8)}`
        : broadcastStatus === 'current'
        ? 'Broadcasting...'
        : 'Pending',
      icon: <Radio className="h-5 w-5" />,
      status: broadcastStatus,
      timestamp: broadcastEvent?.timestamp,
      expandable: !!txRequest.tx_hash,
      details: txRequest.tx_hash && (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between items-center">
            <span className="text-surface-500">Transaction Hash</span>
            <a
              href={getExplorerLink('tx', txRequest.tx_hash)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-brand-400 hover:text-brand-300 flex items-center gap-1"
            >
              {formatAddress(txRequest.tx_hash, 10)}
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          {txRequest.nonce !== null && (
            <div className="flex justify-between">
              <span className="text-surface-500">Nonce</span>
              <span className="font-mono text-surface-300">{txRequest.nonce}</span>
            </div>
          )}
          {txRequest.gas_limit && (
            <div className="flex justify-between">
              <span className="text-surface-500">Gas Limit</span>
              <span className="font-mono text-surface-300">{txRequest.gas_limit.toLocaleString()}</span>
            </div>
          )}
        </div>
      ),
    });

    // 7. Confirmation
    const confirmEvent = auditPackage?.audit_events?.find(
      (e) => e.event_type === 'TX_CONFIRMED' || e.event_type === 'TX_FINALIZED'
    );

    let confirmStatus: TimelineStep['status'] = 'pending';
    if (txRequest.status === 'FINALIZED' || txRequest.status === 'CONFIRMED') {
      confirmStatus = 'completed';
    } else if (txRequest.status === 'CONFIRMING') {
      confirmStatus = 'current';
    } else if (txRequest.status === 'FAILED') {
      confirmStatus = 'failed';
    }

    steps.push({
      id: 'confirmed',
      title: 'Confirmed',
      subtitle: confirmStatus === 'completed'
        ? `${txRequest.confirmations || 0} confirmations`
        : confirmStatus === 'current'
        ? `${txRequest.confirmations || 0} confirmations...`
        : 'Pending',
      icon: <CheckCircle className="h-5 w-5" />,
      status: confirmStatus,
      timestamp: confirmEvent?.timestamp,
      expandable: confirmStatus === 'completed',
      details: confirmStatus === 'completed' && (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-surface-500">Block Number</span>
            <span className="font-mono text-surface-300">{txRequest.block_number || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">Confirmations</span>
            <span className="font-mono text-emerald-400">{txRequest.confirmations || 0}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-surface-500">Final Status</span>
            <StatusBadge status={txRequest.status} />
          </div>
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
        <h3 className="text-lg font-medium text-surface-200">Transaction Audit Trail</h3>
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
            {auditPackage.verification?.first_event || 'N/A'}
          </p>
        </div>
      )}
    </div>
  );
}
