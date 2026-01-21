'use client';

import * as React from 'react';
import { ArrowUpRight, RefreshCw, Check, X, Clock, Shield, ExternalLink } from 'lucide-react';
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
import { txRequestsApi } from '@/lib/api';
import { formatAddress, formatEth, formatRelativeTime, getExplorerLink } from '@/lib/utils';
import { WithdrawRequest } from '@/types';

export default function AdminWithdrawalsPage() {
  const toast = useToastHelpers();
  const [withdrawals, setWithdrawals] = React.useState<WithdrawRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [selectedTx, setSelectedTx] = React.useState<WithdrawRequest | null>(null);
  const [actionType, setActionType] = React.useState<'approve' | 'reject' | null>(null);
  const [rejectReason, setRejectReason] = React.useState('');
  const [isProcessing, setIsProcessing] = React.useState(false);

  const loadData = React.useCallback(async () => {
    try {
      const res = await txRequestsApi.list();
      setWithdrawals(res.data);
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAction = async () => {
    if (!selectedTx) return;
    
    setIsProcessing(true);
    
    try {
      await txRequestsApi.approve(selectedTx.id, {
        decision: actionType === 'approve' ? 'APPROVED' : 'REJECTED',
        comment: actionType === 'reject' ? rejectReason : undefined,
      });
      
      if (actionType === 'approve') {
        toast.success('Withdrawal approved', 'Awaiting user signature');
      } else {
        toast.success('Withdrawal rejected');
      }
      
      setSelectedTx(null);
      setActionType(null);
      setRejectReason('');
      loadData();
    } catch (error) {
      toast.error('Action failed', error instanceof Error ? error.message : 'Please try again');
    } finally {
      setIsProcessing(false);
    }
  };

  const pendingApproval = withdrawals.filter(w => w.status === 'APPROVAL_PENDING');
  const pendingSignature = withdrawals.filter(w => w.status === 'SIGN_PENDING' || w.status === 'APPROVED');
  const inProgress = withdrawals.filter(w => ['BROADCASTED', 'CONFIRMING'].includes(w.status));
  const completed = withdrawals.filter(w => ['FINALIZED', 'REJECTED', 'FAILED'].includes(w.status));

  return (
    <>
      <Header 
        title="Withdrawal Management"
        subtitle="Review and approve outgoing withdrawals"
        actions={
          <Button onClick={() => loadData()} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      />
      
      <PageContainer>
        <div className="space-y-6 animate-stagger">
          {/* Pending Approval */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5 text-amber-400" />
                Pending Approval
                {pendingApproval.length > 0 && (
                  <span className="ml-2 px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 text-sm">
                    {pendingApproval.length}
                  </span>
                )}
              </CardTitle>
              <CardDescription>Withdrawals awaiting admin approval</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                </div>
              ) : pendingApproval.length > 0 ? (
                <div className="space-y-3">
                  {pendingApproval.map((tx) => (
                    <div key={tx.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50 border border-surface-700">
                      <div className="flex items-center gap-4">
                        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400">
                          <ArrowUpRight className="h-6 w-6" />
                        </div>
                        <div>
                          <p className="font-mono text-sm text-surface-200">
                            To: {formatAddress(tx.to_address)}
                          </p>
                          <p className="text-sm text-surface-500">
                            {formatRelativeTime(tx.created_at)} · {tx.approvals.length}/{tx.required_approvals} approvals
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="font-mono text-lg text-surface-200">{formatEth(tx.amount)} ETH</p>
                          <StatusBadge status={tx.status} />
                        </div>
                        <div className="flex gap-2">
                          <Button 
                            variant="success" 
                            size="sm"
                            onClick={() => { setSelectedTx(tx); setActionType('approve'); }}
                          >
                            <Check className="h-4 w-4" />
                            Approve
                          </Button>
                          <Button 
                            variant="destructive" 
                            size="sm"
                            onClick={() => { setSelectedTx(tx); setActionType('reject'); }}
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
                  <p className="text-surface-400">No pending approvals</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Awaiting Signature */}
          {pendingSignature.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-brand-400" />
                  Awaiting User Signature
                  <span className="ml-2 px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-400 text-sm">
                    {pendingSignature.length}
                  </span>
                </CardTitle>
                <CardDescription>Approved withdrawals pending MPC signature</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {pendingSignature.map((tx) => (
                    <div key={tx.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-700">
                          <Shield className="h-5 w-5 text-surface-400" />
                        </div>
                        <div>
                          <p className="font-mono text-sm text-surface-200">{formatAddress(tx.to_address)}</p>
                          <p className="text-sm text-surface-500">{formatRelativeTime(tx.created_at)}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-surface-200">{formatEth(tx.amount)} ETH</p>
                        <StatusBadge status="AWAITING_SIGNATURE" />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* All Withdrawals Table */}
          <Card>
            <CardHeader>
              <CardTitle>All Withdrawals</CardTitle>
              <CardDescription>Complete withdrawal history</CardDescription>
            </CardHeader>
            <CardContent>
              {withdrawals.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-surface-800">
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">To</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Amount</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Status</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Approvals</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">TX Hash</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {withdrawals.map((tx) => (
                        <tr key={tx.id} className="border-b border-surface-800/50 hover:bg-surface-800/30">
                          <td className="py-3 px-4 font-mono text-sm text-surface-200">
                            {formatAddress(tx.to_address)}
                          </td>
                          <td className="py-3 px-4 font-mono text-sm text-surface-200">
                            {formatEth(tx.amount)} ETH
                          </td>
                          <td className="py-3 px-4">
                            <StatusBadge status={tx.status} />
                          </td>
                          <td className="py-3 px-4 text-sm text-surface-400">
                            {tx.approvals.length}/{tx.required_approvals}
                          </td>
                          <td className="py-3 px-4">
                            {tx.tx_hash ? (
                              <a 
                                href={getExplorerLink('tx', tx.tx_hash)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="font-mono text-sm text-brand-400 hover:text-brand-300 flex items-center gap-1"
                              >
                                {formatAddress(tx.tx_hash, 6)}
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            ) : (
                              <span className="text-surface-500">—</span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-sm text-surface-500">
                            {formatRelativeTime(tx.created_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-surface-500">
                  No withdrawals yet
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </PageContainer>

      {/* Confirmation Modal */}
      <Dialog open={!!selectedTx && !!actionType} onOpenChange={() => { setSelectedTx(null); setActionType(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {actionType === 'approve' ? 'Approve Withdrawal' : 'Reject Withdrawal'}
            </DialogTitle>
            <DialogDescription>
              {actionType === 'approve' 
                ? 'This will approve the withdrawal. The user will need to sign the transaction.'
                : 'This will reject the withdrawal request.'}
            </DialogDescription>
          </DialogHeader>

          {selectedTx && (
            <div className="py-4">
              <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-surface-400">To</span>
                  <span className="font-mono text-surface-200">{formatAddress(selectedTx.to_address)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-surface-400">Amount</span>
                  <span className="font-mono text-surface-200">{formatEth(selectedTx.amount)} ETH</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-surface-400">Current Approvals</span>
                  <span className="text-surface-200">{selectedTx.approvals.length}/{selectedTx.required_approvals}</span>
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

              {actionType === 'approve' && (
                <div className="mt-4 p-4 rounded-lg bg-brand-500/10 border border-brand-500/20">
                  <p className="text-sm text-brand-400">
                    After your approval, the user will need to provide their signature using MPC.
                  </p>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => { setSelectedTx(null); setActionType(null); }}>
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

