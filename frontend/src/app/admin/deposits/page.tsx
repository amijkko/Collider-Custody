'use client';

import * as React from 'react';
import { ArrowDownLeft, RefreshCw, Check, X, ExternalLink } from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/modal';
import { Input } from '@/components/ui/input';
import { useToastHelpers } from '@/hooks/use-toast';
import { depositsApi } from '@/lib/api';
import { formatAddress, formatEth, formatRelativeTime, getExplorerLink } from '@/lib/utils';
import { Deposit } from '@/types';

export default function AdminDepositsPage() {
  const toast = useToastHelpers();
  const [deposits, setDeposits] = React.useState<Deposit[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [selectedDeposit, setSelectedDeposit] = React.useState<Deposit | null>(null);
  const [actionType, setActionType] = React.useState<'approve' | 'reject' | null>(null);
  const [rejectReason, setRejectReason] = React.useState('');
  const [isProcessing, setIsProcessing] = React.useState(false);

  const loadData = React.useCallback(async () => {
    setIsLoading(true);
    try {
      // Fetch real deposits from API (admin endpoint)
      const response = await depositsApi.listAdmin();
      console.log('Admin deposits response:', response);
      setDeposits(response.data?.data || []);
    } catch (error) {
      console.error('Failed to load deposits:', error);
      // Don't use toast here to avoid infinite loop
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAction = async () => {
    if (!selectedDeposit) return;
    
    setIsProcessing(true);
    
    try {
      if (actionType === 'approve') {
        await depositsApi.approve(selectedDeposit.id);
        toast.success('Deposit approved', 'Funds credited to user balance');
        setDeposits(prev => prev.map(d => 
          d.id === selectedDeposit.id 
            ? { ...d, status: 'CREDITED' as const, approved_by: 'admin', approved_at: new Date().toISOString() }
            : d
        ));
      } else {
        await depositsApi.reject(selectedDeposit.id, rejectReason || undefined);
        toast.success('Deposit rejected', rejectReason || 'Deposit has been rejected');
        setDeposits(prev => prev.map(d => 
          d.id === selectedDeposit.id 
            ? { ...d, status: 'REJECTED' as const }
            : d
        ));
      }
      
      setSelectedDeposit(null);
      setActionType(null);
      setRejectReason('');
    } catch (error) {
      console.error('Action failed:', error);
      toast.error('Action failed', 'Please try again');
    } finally {
      setIsProcessing(false);
    }
  };

  const pendingDeposits = deposits.filter(d => d.status === 'PENDING_ADMIN');
  const processedDeposits = deposits.filter(d => d.status !== 'PENDING_ADMIN');

  return (
    <>
      <Header 
        title="Deposit Management"
        subtitle="Review and approve incoming deposits"
        actions={
          <Button onClick={() => loadData()} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      />
      
      <PageContainer>
        <div className="space-y-6 animate-stagger">
          {/* Pending Deposits */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ArrowDownLeft className="h-5 w-5 text-amber-400" />
                Pending Approval
                {pendingDeposits.length > 0 && (
                  <span className="ml-2 px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 text-sm">
                    {pendingDeposits.length}
                  </span>
                )}
              </CardTitle>
              <CardDescription>Deposits awaiting admin review</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                </div>
              ) : pendingDeposits.length > 0 ? (
                <div className="space-y-3">
                  {pendingDeposits.map((deposit) => (
                    <div key={deposit.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50 border border-surface-700">
                      <div className="flex items-center gap-4">
                        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
                          <ArrowDownLeft className="h-6 w-6" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="font-mono text-sm text-surface-200">
                              From: {formatAddress(deposit.from_address)}
                            </p>
                            <a 
                              href={getExplorerLink('tx', deposit.tx_hash)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-surface-500 hover:text-surface-300"
                            >
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          </div>
                          <p className="text-sm text-surface-500">
                            {formatRelativeTime(deposit.detected_at)} · Tx: {formatAddress(deposit.tx_hash)}
                          </p>
                          {deposit.kyt_result === 'REVIEW' && (
                            <span className="text-xs text-amber-400">⚠️ KYT flagged for review</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="font-mono text-lg text-surface-200">+{formatEth(deposit.amount)} ETH</p>
                          <StatusBadge status={deposit.kyt_result || 'PENDING'} />
                        </div>
                        <div className="flex gap-2">
                          <Button 
                            variant="success" 
                            size="sm"
                            onClick={() => { setSelectedDeposit(deposit); setActionType('approve'); }}
                          >
                            <Check className="h-4 w-4" />
                            Approve
                          </Button>
                          <Button 
                            variant="destructive" 
                            size="sm"
                            onClick={() => { setSelectedDeposit(deposit); setActionType('reject'); }}
                          >
                            <X className="h-4 w-4" />
                            Reject
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <Check className="h-8 w-8 text-emerald-400 mx-auto mb-2" />
                  <p className="text-surface-400">No pending deposits</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Processed Deposits */}
          <Card>
            <CardHeader>
              <CardTitle>Processed Deposits</CardTitle>
              <CardDescription>Recently processed deposits</CardDescription>
            </CardHeader>
            <CardContent>
              {processedDeposits.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-surface-800">
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">From</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Amount</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">KYT</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Status</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Time</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Approved By</th>
                      </tr>
                    </thead>
                    <tbody>
                      {processedDeposits.map((deposit) => (
                        <tr key={deposit.id} className="border-b border-surface-800/50 hover:bg-surface-800/30">
                          <td className="py-3 px-4 font-mono text-sm text-surface-200">
                            {formatAddress(deposit.from_address)}
                          </td>
                          <td className="py-3 px-4 font-mono text-sm text-surface-200">
                            {formatEth(deposit.amount)} ETH
                          </td>
                          <td className="py-3 px-4">
                            <StatusBadge status={deposit.kyt_result || 'N/A'} />
                          </td>
                          <td className="py-3 px-4">
                            <StatusBadge status={deposit.status} />
                          </td>
                          <td className="py-3 px-4 text-sm text-surface-500">
                            {formatRelativeTime(deposit.detected_at)}
                          </td>
                          <td className="py-3 px-4 text-sm text-surface-400">
                            {deposit.approved_by || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-surface-500">
                  No processed deposits
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </PageContainer>

      {/* Confirmation Modal */}
      <Dialog open={!!selectedDeposit && !!actionType} onOpenChange={() => { setSelectedDeposit(null); setActionType(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {actionType === 'approve' ? 'Approve Deposit' : 'Reject Deposit'}
            </DialogTitle>
            <DialogDescription>
              {actionType === 'approve' 
                ? 'This will credit the funds to the user\'s available balance.'
                : 'This will reject the deposit and funds will not be credited.'}
            </DialogDescription>
          </DialogHeader>

          {selectedDeposit && (
            <div className="py-4">
              <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-surface-400">From</span>
                  <span className="font-mono text-surface-200">{formatAddress(selectedDeposit.from_address)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-surface-400">Amount</span>
                  <span className="font-mono text-surface-200">{formatEth(selectedDeposit.amount)} ETH</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-surface-400">KYT Result</span>
                  <StatusBadge status={selectedDeposit.kyt_result || 'N/A'} />
                </div>
              </div>

              {actionType === 'reject' && (
                <div className="mt-4">
                  <Input
                    label="Reason (optional)"
                    placeholder="Enter rejection reason"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => { setSelectedDeposit(null); setActionType(null); }}>
              Cancel
            </Button>
            <Button 
              variant={actionType === 'approve' ? 'success' : 'destructive'}
              onClick={handleAction}
              isLoading={isProcessing}
            >
              {actionType === 'approve' ? 'Approve' : 'Reject'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
