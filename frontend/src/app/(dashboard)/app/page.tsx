'use client';

import * as React from 'react';
import { Plus, Wallet, ArrowDownLeft, ArrowUpRight, Key, Copy, ExternalLink, RefreshCw } from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/badge';
import { useAuth } from '@/hooks/use-auth';
import { useToastHelpers } from '@/hooks/use-toast';
import { walletsApi, txRequestsApi } from '@/lib/api';
import { formatAddress, formatEth, copyToClipboard, getExplorerLink, formatRelativeTime } from '@/lib/utils';
import { Wallet as WalletType, WithdrawRequest } from '@/types';
import { CreateWalletModal } from '@/components/wallet/create-wallet-modal';

export default function ClientDashboard() {
  const { user } = useAuth();
  const toast = useToastHelpers();
  const [wallets, setWallets] = React.useState<WalletType[]>([]);
  const [transactions, setTransactions] = React.useState<WithdrawRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [showCreateModal, setShowCreateModal] = React.useState(false);
  const [availableBalance, setAvailableBalance] = React.useState<number>(0);
  const [pendingBalance, setPendingBalance] = React.useState<number>(0);

  const loadData = React.useCallback(async () => {
    try {
      const [walletsRes, txRes] = await Promise.all([
        walletsApi.list(),
        txRequestsApi.list(),
      ]);
      // Only show MPC wallets to users (hide DEV_SIGNER)
      const mpcWallets = walletsRes.data.filter((w: WalletType) => w.custody_backend === 'MPC_TECDSA');
      setWallets(mpcWallets);

      // Load ledger balance for primary MPC wallet
      const primaryMpc = mpcWallets.find((w: WalletType) => w.status === 'ACTIVE');
      if (primaryMpc) {
        try {
          const balanceRes = await walletsApi.getLedgerBalance(primaryMpc.id);
          setAvailableBalance(parseFloat(balanceRes.data.available_eth));
          setPendingBalance(parseFloat(balanceRes.data.pending_eth));
        } catch {
          setAvailableBalance(0);
          setPendingBalance(0);
        }
      }
      
      // Filter transactions for MPC wallets only
      const mpcWalletIds = mpcWallets.map((w: WalletType) => w.id);
      setTransactions(txRes.data.filter((tx: WithdrawRequest) => mpcWalletIds.includes(tx.wallet_id)).slice(0, 5));
    } catch {
      toast.error('Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCopyAddress = async (address: string) => {
    const success = await copyToClipboard(address);
    if (success) {
      toast.success('Address copied');
    }
  };

  const primaryWallet = wallets.find(w => w.status === 'ACTIVE');

  return (
    <>
      <Header 
        title={`Welcome back, ${user?.username}`}
        subtitle="Manage your crypto assets"
        actions={
          <Button onClick={() => loadData()} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      />
      
      <PageContainer>
        <div className="space-y-6 animate-stagger">
          {/* Wallet Card */}
          <Card className="overflow-hidden">
            <div className="bg-gradient-to-r from-brand-600 to-brand-500 p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/20 backdrop-blur">
                    <Wallet className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <p className="text-sm text-white/80">Your Wallet</p>
                    {primaryWallet ? (
                      <div className="flex items-center gap-2">
                        <p className="text-lg font-mono text-white">
                          {formatAddress(primaryWallet.address, 6)}
                        </p>
                        <button 
                          onClick={() => primaryWallet.address && handleCopyAddress(primaryWallet.address)}
                          className="text-white/60 hover:text-white transition-colors"
                        >
                          <Copy className="h-4 w-4" />
                        </button>
                        {primaryWallet.address && (
                          <a 
                            href={getExplorerLink('address', primaryWallet.address)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-white/60 hover:text-white transition-colors"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        )}
                      </div>
                    ) : (
                      <p className="text-white/60">No wallet created yet</p>
                    )}
                  </div>
                </div>
                {primaryWallet && (
                  <StatusBadge 
                    status={primaryWallet.custody_backend === 'MPC_TECDSA' ? 'MPC 2-of-3' : 'DEV'} 
                  />
                )}
              </div>
            </div>

            <CardContent className="p-6">
              {primaryWallet ? (
                <div className="grid grid-cols-3 gap-6">
                  <div>
                    <p className="text-sm text-surface-500">Pending Approval</p>
                    <p className="text-2xl font-semibold text-amber-400">
                      {pendingBalance.toFixed(6)} <span className="text-sm text-amber-400/60">ETH</span>
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-surface-500">Available</p>
                    <p className="text-2xl font-semibold text-emerald-400">
                      {availableBalance.toFixed(6)} <span className="text-sm text-emerald-400/60">ETH</span>
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-surface-500">Total</p>
                    <p className="text-2xl font-semibold text-surface-100">
                      {(availableBalance + pendingBalance).toFixed(6)} <span className="text-sm text-surface-500">ETH</span>
                    </p>
                  </div>
                </div>
              ) : (
                <div className="text-center py-4">
                  <p className="text-surface-400 mb-4">Create a wallet to start managing your crypto</p>
                  <Button onClick={() => setShowCreateModal(true)}>
                    <Plus className="h-4 w-4" />
                    Create MPC Wallet
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <div className="grid grid-cols-3 gap-4">
            <Card className="hover:border-brand-500/50 transition-colors cursor-pointer group">
              <CardContent className="p-6 flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 group-hover:bg-emerald-500/20 transition-colors">
                  <ArrowDownLeft className="h-6 w-6" />
                </div>
                <div>
                  <p className="font-medium text-surface-100">Deposit</p>
                  <p className="text-sm text-surface-500">Receive ETH</p>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:border-brand-500/50 transition-colors cursor-pointer group">
              <CardContent className="p-6 flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500/10 text-brand-400 group-hover:bg-brand-500/20 transition-colors">
                  <ArrowUpRight className="h-6 w-6" />
                </div>
                <div>
                  <p className="font-medium text-surface-100">Withdraw</p>
                  <p className="text-sm text-surface-500">Send ETH</p>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:border-brand-500/50 transition-colors cursor-pointer group">
              <CardContent className="p-6 flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 group-hover:bg-amber-500/20 transition-colors">
                  <Key className="h-6 w-6" />
                </div>
                <div>
                  <p className="font-medium text-surface-100">Sign</p>
                  <p className="text-sm text-surface-500">Pending signatures</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Recent Transactions */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Your recent transactions</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                </div>
              ) : transactions.length > 0 ? (
                <div className="space-y-3">
                  {transactions.map((tx) => (
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
                        <p className="font-mono text-surface-200">-{formatEth(tx.amount)} ETH</p>
                        <StatusBadge status={tx.status} />
                      </div>
                    </div>
                  ))}
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

      <CreateWalletModal 
        open={showCreateModal} 
        onOpenChange={setShowCreateModal}
        onSuccess={loadData}
      />
    </>
  );
}

