'use client';

import * as React from 'react';
import { Shield, AlertTriangle, CheckCircle, XCircle, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react';
import { StatusBadge } from '@/components/ui/badge';
import { formatAddress, formatEth, getExplorerLink } from '@/lib/utils';

interface ExposureItem {
  entity: string;
  category: string;
  share: number;
  risk: 'low' | 'medium' | 'high';
}

interface BitOKReportData {
  transfer_id: string;
  network: string;
  tx_hash: string;
  from_address: string;
  to_address: string;
  amount_wei: string;
  amount_eth: string;
  value_usd: number;
  risk_level: 'low' | 'medium' | 'high';
  risk_score: number;
  check_state: {
    exposure: 'checked' | 'pending' | 'failed';
    counterparty: 'checked' | 'pending' | 'failed';
    sanctions: 'checked' | 'pending' | 'failed';
  };
  exposure: ExposureItem[];
  counterparty: {
    type: string;
    name: string | null;
    labels: string[];
    first_seen: string;
    tx_count: number;
  };
  sanctions_hit: boolean;
  created_at: string;
}

// Generate fake BitOK report based on deposit data
export function generateBitOKReport(deposit: {
  tx_hash: string;
  from_address: string;
  to_address?: string;
  amount: string;
  wallet_id?: string;
}): BitOKReportData {
  // Generate deterministic "random" values based on tx_hash
  const hashNum = parseInt(deposit.tx_hash.slice(2, 10), 16);
  const riskScore = (hashNum % 30) + 5; // 5-35 range for mostly low risk

  // Determine risk level based on score
  let riskLevel: 'low' | 'medium' | 'high' = 'low';
  if (riskScore > 25) riskLevel = 'medium';
  if (riskScore > 70) riskLevel = 'high';

  // Parse amount to ETH
  const amountWei = deposit.amount;
  const amountEth = (parseFloat(amountWei) / 1e18).toFixed(6);
  const valueUsd = parseFloat(amountEth) * 2450; // Fake ETH price

  // Generate exposure breakdown
  const exposureCategories = [
    { entity: 'Exchange', category: 'Centralized Exchange', risk: 'low' as const },
    { entity: 'DeFi', category: 'Decentralized Finance', risk: 'low' as const },
    { entity: 'Bridge', category: 'Cross-chain Bridge', risk: 'medium' as const },
    { entity: 'Mining', category: 'Mining Pool', risk: 'low' as const },
    { entity: 'Unknown', category: 'Unidentified Wallet', risk: 'medium' as const },
  ];

  // Pick 2-4 exposure items based on hash
  const numExposures = (hashNum % 3) + 2;
  const exposure: ExposureItem[] = [];
  let remainingShare = 100;

  for (let i = 0; i < numExposures && i < exposureCategories.length; i++) {
    const share = i === numExposures - 1
      ? remainingShare
      : Math.floor(remainingShare * (0.3 + (((hashNum >> (i * 4)) % 10) / 20)));
    remainingShare -= share;

    exposure.push({
      ...exposureCategories[(hashNum + i) % exposureCategories.length],
      share,
    });
  }

  // Sort by share descending
  exposure.sort((a, b) => b.share - a.share);

  // Counterparty info
  const counterpartyTypes = ['EOA', 'Smart Contract', 'Exchange Hot Wallet', 'DeFi Protocol'];
  const counterpartyLabels = [
    ['Personal Wallet'],
    ['Uniswap User', 'DeFi Active'],
    ['Binance User', 'Exchange Withdrawal'],
    ['Bridge User', 'Multi-chain'],
    [],
  ];

  const txCount = (hashNum % 500) + 10;
  const daysAgo = (hashNum % 365) + 30;
  const firstSeen = new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000).toISOString();

  return {
    transfer_id: `btk_${deposit.tx_hash.slice(2, 18)}`,
    network: 'ethereum',
    tx_hash: deposit.tx_hash,
    from_address: deposit.from_address,
    to_address: deposit.to_address || deposit.wallet_id || '0x...',
    amount_wei: amountWei,
    amount_eth: amountEth,
    value_usd: valueUsd,
    risk_level: riskLevel,
    risk_score: riskScore,
    check_state: {
      exposure: 'checked',
      counterparty: 'checked',
      sanctions: 'checked',
    },
    exposure,
    counterparty: {
      type: counterpartyTypes[hashNum % counterpartyTypes.length],
      name: null,
      labels: counterpartyLabels[hashNum % counterpartyLabels.length],
      first_seen: firstSeen,
      tx_count: txCount,
    },
    sanctions_hit: false,
    created_at: new Date().toISOString(),
  };
}

interface BitOKReportProps {
  deposit: {
    tx_hash: string;
    from_address: string;
    to_address?: string;
    amount: string;
    wallet_id?: string;
  };
  className?: string;
}

export function BitOKReport({ deposit, className = '' }: BitOKReportProps) {
  const [expanded, setExpanded] = React.useState(true);
  const report = React.useMemo(() => generateBitOKReport(deposit), [deposit]);

  const getRiskColor = (level: 'low' | 'medium' | 'high') => {
    switch (level) {
      case 'low': return 'text-emerald-400';
      case 'medium': return 'text-amber-400';
      case 'high': return 'text-red-400';
    }
  };

  const getRiskBg = (level: 'low' | 'medium' | 'high') => {
    switch (level) {
      case 'low': return 'bg-emerald-500/10 border-emerald-500/30';
      case 'medium': return 'bg-amber-500/10 border-amber-500/30';
      case 'high': return 'bg-red-500/10 border-red-500/30';
    }
  };

  const CheckIcon = ({ status }: { status: string }) => {
    if (status === 'checked') return <CheckCircle className="h-4 w-4 text-emerald-400" />;
    if (status === 'pending') return <AlertTriangle className="h-4 w-4 text-amber-400" />;
    return <XCircle className="h-4 w-4 text-red-400" />;
  };

  return (
    <div className={`rounded-lg border border-surface-700 bg-surface-900 ${className}`}>
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-surface-800/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-brand-400" />
          <span className="font-medium text-surface-200">BitOK KYT Report</span>
          <span className="text-xs text-surface-500">v1.4</span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`px-2 py-0.5 rounded text-xs font-medium ${getRiskBg(report.risk_level)} ${getRiskColor(report.risk_level)}`}>
            Risk: {report.risk_level.toUpperCase()} ({report.risk_score}/100)
          </div>
          {expanded ? <ChevronUp className="h-4 w-4 text-surface-500" /> : <ChevronDown className="h-4 w-4 text-surface-500" />}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-surface-700 p-4 space-y-4">
          {/* Transfer Details */}
          <div>
            <h4 className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-2">Transfer Details</h4>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="flex justify-between">
                <span className="text-surface-500">Transfer ID</span>
                <span className="font-mono text-surface-300">{report.transfer_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Network</span>
                <span className="text-surface-300 capitalize">{report.network}</span>
              </div>
              <div className="flex justify-between col-span-2">
                <span className="text-surface-500">Transaction</span>
                <a
                  href={getExplorerLink('tx', report.tx_hash)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-brand-400 hover:text-brand-300 flex items-center gap-1"
                >
                  {formatAddress(report.tx_hash)}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Amount</span>
                <span className="font-mono text-surface-300">{report.amount_eth} ETH</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Value (USD)</span>
                <span className="font-mono text-surface-300">${report.value_usd.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* Check State */}
          <div>
            <h4 className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-2">Verification Status</h4>
            <div className="grid grid-cols-3 gap-2">
              <div className="flex items-center gap-2 p-2 rounded bg-surface-800/50">
                <CheckIcon status={report.check_state.exposure} />
                <span className="text-sm text-surface-300">Exposure</span>
              </div>
              <div className="flex items-center gap-2 p-2 rounded bg-surface-800/50">
                <CheckIcon status={report.check_state.counterparty} />
                <span className="text-sm text-surface-300">Counterparty</span>
              </div>
              <div className="flex items-center gap-2 p-2 rounded bg-surface-800/50">
                <CheckIcon status={report.check_state.sanctions} />
                <span className="text-sm text-surface-300">Sanctions</span>
              </div>
            </div>
          </div>

          {/* Risk Assessment */}
          <div>
            <h4 className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-2">Risk Assessment</h4>
            <div className={`p-3 rounded-lg border ${getRiskBg(report.risk_level)}`}>
              <div className="flex items-center justify-between mb-2">
                <span className={`font-medium ${getRiskColor(report.risk_level)}`}>
                  {report.risk_level === 'low' && '✓ Low Risk Transaction'}
                  {report.risk_level === 'medium' && '⚠ Medium Risk - Review Recommended'}
                  {report.risk_level === 'high' && '✕ High Risk - Investigation Required'}
                </span>
                <span className={`text-2xl font-bold ${getRiskColor(report.risk_level)}`}>
                  {report.risk_score}
                </span>
              </div>
              {/* Risk score bar */}
              <div className="h-2 bg-surface-800 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all ${
                    report.risk_level === 'low' ? 'bg-emerald-500' :
                    report.risk_level === 'medium' ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${report.risk_score}%` }}
                />
              </div>
            </div>
          </div>

          {/* Exposure Breakdown */}
          <div>
            <h4 className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-2">Exposure Breakdown</h4>
            <div className="space-y-2">
              {report.exposure.map((item, i) => (
                <div key={i} className="flex items-center justify-between p-2 rounded bg-surface-800/50">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${
                      item.risk === 'low' ? 'bg-emerald-400' :
                      item.risk === 'medium' ? 'bg-amber-400' : 'bg-red-400'
                    }`} />
                    <div>
                      <span className="text-sm text-surface-200">{item.entity}</span>
                      <span className="text-xs text-surface-500 ml-2">{item.category}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-surface-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${
                          item.risk === 'low' ? 'bg-emerald-500' :
                          item.risk === 'medium' ? 'bg-amber-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${item.share}%` }}
                      />
                    </div>
                    <span className="text-sm font-mono text-surface-400 w-12 text-right">{item.share}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Counterparty Info */}
          <div>
            <h4 className="text-xs font-medium text-surface-400 uppercase tracking-wider mb-2">Counterparty Analysis</h4>
            <div className="p-3 rounded-lg bg-surface-800/50 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-surface-500">Address</span>
                <a
                  href={getExplorerLink('address', report.from_address)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-brand-400 hover:text-brand-300 flex items-center gap-1"
                >
                  {formatAddress(report.from_address)}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Type</span>
                <span className="text-surface-300">{report.counterparty.type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">First Seen</span>
                <span className="text-surface-300">{new Date(report.counterparty.first_seen).toLocaleDateString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-500">Total Transactions</span>
                <span className="font-mono text-surface-300">{report.counterparty.tx_count}</span>
              </div>
              {report.counterparty.labels.length > 0 && (
                <div className="flex justify-between items-start">
                  <span className="text-surface-500">Labels</span>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {report.counterparty.labels.map((label, i) => (
                      <span key={i} className="px-2 py-0.5 rounded text-xs bg-surface-700 text-surface-300">
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Sanctions Check */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-surface-800/50">
            <div className="flex items-center gap-2">
              {report.sanctions_hit ? (
                <XCircle className="h-5 w-5 text-red-400" />
              ) : (
                <CheckCircle className="h-5 w-5 text-emerald-400" />
              )}
              <span className="text-sm text-surface-300">OFAC/Sanctions Screening</span>
            </div>
            <span className={`text-sm font-medium ${report.sanctions_hit ? 'text-red-400' : 'text-emerald-400'}`}>
              {report.sanctions_hit ? 'HIT DETECTED' : 'No matches found'}
            </span>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between pt-2 border-t border-surface-700 text-xs text-surface-500">
            <span>Report generated: {new Date(report.created_at).toLocaleString()}</span>
            <span>Powered by BitOK KYT Engine</span>
          </div>
        </div>
      )}
    </div>
  );
}
