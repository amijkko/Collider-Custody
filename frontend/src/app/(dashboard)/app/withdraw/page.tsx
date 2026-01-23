'use client';

import * as React from 'react';
import { ArrowUpRight, RefreshCw, AlertCircle } from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/badge';
import { useToastHelpers } from '@/hooks/use-toast';
import { walletsApi, txRequestsApi } from '@/lib/api';
import { formatAddress, formatRelativeTime, isValidAddress, isValidAmount } from '@/lib/utils';
import { Wallet, WithdrawRequest } from '@/types';

export default function WithdrawPage() {
  const toast = useToastHelpers();
  const [wallet, setWallet] = React.useState<Wallet | null>(null);
  const [withdrawals, setWithdrawals] = React.useState<WithdrawRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [availableBalance, setAvailableBalance] = React.useState<number>(0);
  const [isLoadingBalance, setIsLoadingBalance] = React.useState(false);
  
  // Form state
  const [toAddress, setToAddress] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  const loadData = React.useCallback(async () => {
    try {
      const [walletsRes, txRes] = await Promise.all([
        walletsApi.list(),
        txRequestsApi.list(),
      ]);
      
      // Only show MPC wallets to users (hide DEV_SIGNER)
      const mpcWallet = walletsRes.data.find(w => 
        w.status === 'ACTIVE' && w.custody_backend === 'MPC_TECDSA'
      );
      setWallet(mpcWallet || null);
      
      // Load ledger balance if wallet found (only CREDITED deposits are available)
      if (mpcWallet) {
        setIsLoadingBalance(true);
        try {
          const balanceRes = await walletsApi.getLedgerBalance(mpcWallet.id);
          setAvailableBalance(parseFloat(balanceRes.data.available_eth));
        } catch (balErr) {
          console.error('Failed to load balance:', balErr);
          setAvailableBalance(0);
        } finally {
          setIsLoadingBalance(false);
        }
      }
      
      // Show withdrawals only for MPC wallets
      const mpcWalletIds = walletsRes.data
        .filter(w => w.custody_backend === 'MPC_TECDSA')
        .map(w => w.id);
      setWithdrawals(txRes.data.filter(tx => mpcWalletIds.includes(tx.wallet_id)));
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const validate = () => {
    const newErrors: Record<string, string> = {};
    
    if (!isValidAddress(toAddress)) {
      newErrors.toAddress = 'Please enter a valid Ethereum address';
    }
    if (!isValidAmount(amount)) {
      newErrors.amount = 'Please enter a valid amount';
    }
    if (parseFloat(amount) > availableBalance) {
      newErrors.amount = 'Insufficient balance';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validate() || !wallet) return;
    
    setIsSubmitting(true);

    try {
      await txRequestsApi.create({
        wallet_id: wallet.id,
        tx_type: 'WITHDRAW',
        to_address: toAddress,
        asset: 'ETH',
        amount: amount,
      });

      toast.success('Withdrawal requested', 'Pending admin approval');
      setToAddress('');
      setAmount('');
      loadData();
    } catch (error) {
      toast.error('Failed to create withdrawal', error instanceof Error ? error.message : 'Please try again');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <Header 
        title="Withdraw"
        subtitle="Send ETH from your wallet"
        actions={
          <Button onClick={() => loadData()} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      />
      
      <PageContainer>
        <div className="grid grid-cols-2 gap-6 max-w-6xl animate-stagger">
          {/* Withdraw Form */}
          <Card>
            <CardHeader>
              <CardTitle>New Withdrawal</CardTitle>
              <CardDescription>
                Withdrawals require admin approval and your signature
              </CardDescription>
            </CardHeader>
            <CardContent>
              {wallet ? (
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700">
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-surface-400">Wallet</span>
                      <span className="font-mono text-surface-300">{formatAddress(wallet.address)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-surface-400">Available Balance</span>
                      {isLoadingBalance ? (
                        <span className="text-surface-500">Loading...</span>
                      ) : (
                        <span className="font-mono text-emerald-400">{availableBalance.toFixed(6)} ETH</span>
                      )}
                    </div>
                  </div>

                  <Input
                    label="Recipient Address"
                    placeholder="0x..."
                    value={toAddress}
                    onChange={(e) => setToAddress(e.target.value)}
                    error={errors.toAddress}
                  />

                  <div className="space-y-1.5">
                    <label className="block text-sm font-medium text-surface-300">
                      Amount (ETH)
                    </label>
                    <div className="relative">
                      <Input
                        placeholder="0.0"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        error={errors.amount}
                      />
                      <button
                        type="button"
                        onClick={() => setAmount(availableBalance.toString())}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-brand-400 hover:text-brand-300"
                      >
                        MAX
                      </button>
                    </div>
                  </div>

                  <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/20">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
                      <p className="text-sm text-amber-400">
                        After admin approval, you'll need to sign the transaction using your password.
                      </p>
                    </div>
                  </div>

                  <Button type="submit" className="w-full" isLoading={isSubmitting}>
                    Request Withdrawal
                  </Button>
                </form>
              ) : (
                <div className="text-center py-8">
                  <p className="text-surface-400 mb-4">No MPC wallet found. Please contact admin to create one.</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Withdrawal History */}
          <Card>
            <CardHeader>
              <CardTitle>Withdrawal History</CardTitle>
              <CardDescription>Your withdrawal requests</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                </div>
              ) : withdrawals.length > 0 ? (
                <div className="space-y-3">
                  {withdrawals.map((tx) => (
                    <div key={tx.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400">
                          <ArrowUpRight className="h-5 w-5" />
                        </div>
                        <div>
                          <p className="font-mono text-sm text-surface-200">
                            To: {formatAddress(tx.to_address)}
                          </p>
                          <p className="text-sm text-surface-500">
                            {formatRelativeTime(tx.created_at)}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-surface-200">-{tx.amount} ETH</p>
                        <StatusBadge status={tx.status} />
                      </div>
                    </div>
                  ))}
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
    </>
  );
}

