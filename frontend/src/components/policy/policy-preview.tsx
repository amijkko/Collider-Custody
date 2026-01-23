'use client';

import * as React from 'react';
import { Shield, ShieldAlert, ShieldCheck, ShieldX, Clock, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { PolicyEvalPreview } from '@/types';

interface PolicyPreviewProps {
  preview: PolicyEvalPreview | null;
  isLoading?: boolean;
  error?: string | null;
}

export function PolicyPreview({ preview, isLoading, error }: PolicyPreviewProps) {
  if (isLoading) {
    return (
      <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700 animate-pulse">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-surface-500" />
          <span className="text-sm text-surface-400">Evaluating policy...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20">
        <div className="flex items-center gap-2">
          <XCircle className="h-4 w-4 text-red-400" />
          <span className="text-sm text-red-400">{error}</span>
        </div>
      </div>
    );
  }

  if (!preview) {
    return null;
  }

  const isBlocked = !preview.allowed;
  const isDenylist = preview.address_status === 'denylist';
  const isUnknown = preview.address_status === 'unknown';
  const isFastTrack = preview.allowed && !preview.kyt_required && !preview.approval_required;

  // Determine the visual style based on result
  let containerClass = 'p-4 rounded-lg border';
  let Icon = Shield;
  let iconClass = 'h-5 w-5';
  let titleClass = 'font-medium';

  if (isBlocked) {
    containerClass += ' bg-red-500/10 border-red-500/30';
    Icon = ShieldX;
    iconClass += ' text-red-400';
    titleClass += ' text-red-400';
  } else if (isFastTrack) {
    containerClass += ' bg-emerald-500/10 border-emerald-500/30';
    Icon = ShieldCheck;
    iconClass += ' text-emerald-400';
    titleClass += ' text-emerald-400';
  } else {
    containerClass += ' bg-amber-500/10 border-amber-500/30';
    Icon = ShieldAlert;
    iconClass += ' text-amber-400';
    titleClass += ' text-amber-400';
  }

  return (
    <div className={containerClass}>
      <div className="flex items-start gap-3">
        <Icon className={iconClass} />
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between mb-2">
            <span className={titleClass}>
              {isBlocked ? 'Transaction Blocked' : isFastTrack ? 'Fast Track' : 'Requires Verification'}
            </span>
            {preview.policy_version && (
              <span className="text-xs text-surface-500 font-mono">
                {preview.policy_version}
              </span>
            )}
          </div>

          {/* Address Status */}
          <div className="mb-3">
            <AddressStatusBadge
              status={preview.address_status}
              label={preview.address_label}
            />
          </div>

          {/* Matched Rules */}
          {preview.matched_rules.length > 0 && (
            <div className="mb-3">
              <div className="text-xs text-surface-500 mb-1">Matched Rules</div>
              <div className="flex flex-wrap gap-1">
                {preview.matched_rules.map((rule) => (
                  <span
                    key={rule}
                    className="px-2 py-0.5 text-xs font-mono rounded bg-surface-700 text-surface-300"
                  >
                    {rule}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Reasons */}
          {preview.reasons.length > 0 && (
            <div className="mb-3">
              <div className="text-xs text-surface-500 mb-1">Reason</div>
              <p className="text-sm text-surface-300">{preview.reasons[0]}</p>
            </div>
          )}

          {/* Controls Required */}
          {preview.allowed && (
            <div className="flex items-center gap-4 text-xs">
              <ControlBadge
                enabled={preview.kyt_required}
                label="KYT Check"
                enabledColor="amber"
              />
              <ControlBadge
                enabled={preview.approval_required}
                label={`Approval${preview.approval_count > 0 ? ` (${preview.approval_count})` : ''}`}
                enabledColor="amber"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface AddressStatusBadgeProps {
  status: 'allowlist' | 'denylist' | 'unknown';
  label: string | null;
}

function AddressStatusBadge({ status, label }: AddressStatusBadgeProps) {
  let bgClass = '';
  let textClass = '';
  let Icon = Shield;
  let statusText = '';

  switch (status) {
    case 'allowlist':
      bgClass = 'bg-emerald-500/10';
      textClass = 'text-emerald-400';
      Icon = CheckCircle2;
      statusText = 'Allowlisted';
      break;
    case 'denylist':
      bgClass = 'bg-red-500/10';
      textClass = 'text-red-400';
      Icon = XCircle;
      statusText = 'Denylisted';
      break;
    case 'unknown':
      bgClass = 'bg-surface-700/50';
      textClass = 'text-surface-400';
      Icon = AlertTriangle;
      statusText = 'Unknown Address';
      break;
  }

  return (
    <div className={`inline-flex items-center gap-2 px-2 py-1 rounded ${bgClass}`}>
      <Icon className={`h-3.5 w-3.5 ${textClass}`} />
      <span className={`text-xs ${textClass}`}>{statusText}</span>
      {label && (
        <span className="text-xs text-surface-500">({label})</span>
      )}
    </div>
  );
}

interface ControlBadgeProps {
  enabled: boolean;
  label: string;
  enabledColor: 'amber' | 'emerald' | 'red';
}

function ControlBadge({ enabled, label, enabledColor }: ControlBadgeProps) {
  const colorMap = {
    amber: 'text-amber-400',
    emerald: 'text-emerald-400',
    red: 'text-red-400',
  };

  return (
    <div className="flex items-center gap-1">
      {enabled ? (
        <CheckCircle2 className={`h-3.5 w-3.5 ${colorMap[enabledColor]}`} />
      ) : (
        <XCircle className="h-3.5 w-3.5 text-surface-500" />
      )}
      <span className={enabled ? colorMap[enabledColor] : 'text-surface-500'}>
        {label}
      </span>
    </div>
  );
}

// Compact version for transaction list
export function PolicyResultBadge({ policyResult }: { policyResult: any }) {
  if (!policyResult) return null;

  const isBlocked = !policyResult.allowed;
  const isFastTrack = policyResult.allowed && !policyResult.kyt_required && !policyResult.approval_required;

  let className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs';
  let Icon = Shield;

  if (isBlocked) {
    className += ' bg-red-500/10 text-red-400';
    Icon = ShieldX;
  } else if (isFastTrack) {
    className += ' bg-emerald-500/10 text-emerald-400';
    Icon = ShieldCheck;
  } else {
    className += ' bg-amber-500/10 text-amber-400';
    Icon = ShieldAlert;
  }

  return (
    <span className={className}>
      <Icon className="h-3 w-3" />
      {policyResult.matched_rules?.[0] || policyResult.decision}
    </span>
  );
}
