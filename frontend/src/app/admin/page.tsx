'use client';

import * as React from 'react';
import { ArrowDownLeft, ArrowUpRight, Users, AlertTriangle, CheckCircle2, Clock, Shield, RefreshCw } from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/badge';
import { useToastHelpers } from '@/hooks/use-toast';
import { walletsApi, txRequestsApi } from '@/lib/api';
import { formatAddress, formatEth, formatRelativeTime } from '@/lib/utils';
import { Wallet, WithdrawRequest } from '@/types';

export default function AdminDashboard() {
  const toast = useToastHelpers();
  const [wallets, setWallets] = React.useState<Wallet[]>([]);
  const [transactions, setTransactions] = React.useState<WithdrawRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);

  const loadData = React.useCallback(async () => {
    try {
      const [walletsRes, txRes] = await Promise.all([
        walletsApi.list(),
        txRequestsApi.list(),
      ]);
      setWallets(walletsRes.data);
      setTransactions(txRes.data);
    } catch (error) {
      toast.error('Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const pendingDeposits = 3; // Mock
  const pendingWithdrawals = transactions.filter(tx => tx.status === 'APPROVAL_PENDING').length;
  const pendingKYT = transactions.filter(tx => tx.status === 'KYT_REVIEW').length;

  const stats = [
    {
      label: 'Pending Deposits',
      value: pendingDeposits,
      icon: ArrowDownLeft,
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-500/10',
    },
    {
      label: 'Pending Withdrawals',
      value: pendingWithdrawals,
      icon: ArrowUpRight,
      color: 'text-brand-400',
      bgColor: 'bg-brand-500/10',
    },
    {
      label: 'KYT Reviews',
      value: pendingKYT,
      icon: AlertTriangle,
      color: 'text-amber-400',
      bgColor: 'bg-amber-500/10',
    },
    {
      label: 'Active Wallets',
      value: wallets.filter(w => w.status === 'ACTIVE').length,
      icon: Shield,
      color: 'text-purple-400',
      bgColor: 'bg-purple-500/10',
    },
  ];

  return (
    <>
      <Header 
        title="Admin Dashboard"
        subtitle="Manage deposits, withdrawals and compliance"
        actions={
          <Button onClick={() => loadData()} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      />
      
      <PageContainer>
        <div className="space-y-6 animate-stagger">
          {/* Stats Grid */}
          <div className="grid grid-cols-4 gap-4">
            {stats.map((stat) => (
              <Card key={stat.label}>
                <CardContent className="p-6">
                  <div className="flex items-center gap-4">
                    <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${stat.bgColor} ${stat.color}`}>
                      <stat.icon className="h-6 w-6" />
                    </div>
                    <div>
                      <p className="text-2xl font-semibold text-surface-100">{stat.value}</p>
                      <p className="text-sm text-surface-500">{stat.label}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Recent Actions Grid */}
          <div className="grid grid-cols-2 gap-6">
            {/* Pending Approvals */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5 text-amber-400" />
                  Pending Approvals
                </CardTitle>
                <CardDescription>Withdrawals awaiting admin approval</CardDescription>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="flex justify-center py-8">
                    <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                  </div>
                ) : transactions.filter(tx => tx.status === 'APPROVAL_PENDING').length > 0 ? (
                  <div className="space-y-3">
                    {transactions
                      .filter(tx => tx.status === 'APPROVAL_PENDING')
                      .slice(0, 5)
                      .map((tx) => (
                        <div key={tx.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50">
                          <div className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-700">
                              <ArrowUpRight className="h-5 w-5 text-surface-400" />
                            </div>
                            <div>
                              <p className="font-medium text-surface-200">{formatAddress(tx.to_address)}</p>
                              <p className="text-sm text-surface-500">{formatRelativeTime(tx.created_at)}</p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="font-mono text-surface-200">{formatEth(tx.amount)} ETH</p>
                            <p className="text-xs text-surface-500">
                              {tx.approvals.length}/{tx.required_approvals} approvals
                            </p>
                          </div>
                        </div>
                      ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <CheckCircle2 className="h-8 w-8 text-emerald-400 mx-auto mb-2" />
                    <p className="text-surface-400">No pending approvals</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Recent Wallets */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Shield className="h-5 w-5 text-brand-400" />
                  Recent Wallets
                </CardTitle>
                <CardDescription>Recently created MPC wallets</CardDescription>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="flex justify-center py-8">
                    <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                  </div>
                ) : wallets.length > 0 ? (
                  <div className="space-y-3">
                    {wallets.slice(0, 5).map((wallet) => (
                      <div key={wallet.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-700">
                            <Shield className="h-5 w-5 text-surface-400" />
                          </div>
                          <div>
                            <p className="font-mono text-sm text-surface-200">{formatAddress(wallet.address)}</p>
                            <p className="text-xs text-surface-500">{wallet.subject_id}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <StatusBadge status={wallet.custody_backend} />
                          <p className="text-xs text-surface-500 mt-1">{wallet.wallet_type}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-surface-500">
                    No wallets yet
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* All Transactions */}
          <Card>
            <CardHeader>
              <CardTitle>All Transactions</CardTitle>
              <CardDescription>Complete transaction history</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                </div>
              ) : transactions.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-surface-800">
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">To</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Amount</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Status</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Approvals</th>
                        <th className="text-left py-3 px-4 text-sm font-medium text-surface-400">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.map((tx) => (
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
                  No transactions yet
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </PageContainer>
    </>
  );
}

