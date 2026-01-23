'use client';

import * as React from 'react';
import { QrCode, Copy, ExternalLink, RefreshCw, ArrowDownLeft } from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/badge';
import { walletsApi, depositsApi } from '@/lib/api';
import { formatAddress, copyToClipboard, getExplorerLink, formatEth, formatRelativeTime } from '@/lib/utils';
import { Wallet, Deposit } from '@/types';

export default function DepositPage() {
  const [wallet, setWallet] = React.useState<Wallet | null>(null);
  const [deposits, setDeposits] = React.useState<Deposit[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // IMPORTANT: All hooks MUST be before any conditional returns!
  const loadData = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const walletsRes = await walletsApi.list();
      // Only show MPC wallets to users (hide DEV_SIGNER)
      const mpcWallet = walletsRes.data?.find((w: Wallet) => 
        w.status === 'ACTIVE' && w.custody_backend === 'MPC_TECDSA'
      );
      setWallet(mpcWallet || null);
      
      // Fetch real deposits from API
      if (mpcWallet) {
        const depositsRes = await depositsApi.list({ wallet_id: mpcWallet.id });
        // API returns { data: Deposit[], total, correlation_id }
        setDeposits(depositsRes.data || []);
      } else {
        setDeposits([]);
      }
    } catch (err) {
      console.error('Failed to load data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCopy = async (text: string) => {
    await copyToClipboard(text);
  };

  // Conditional renders AFTER all hooks
  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <Header title="Deposit" subtitle="Receive ETH to your wallet" />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500 mx-auto mb-4"></div>
            <p className="text-gray-400">Loading wallets...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col h-full">
        <Header title="Deposit" subtitle="Receive ETH to your wallet" />
        <PageContainer>
          <Card>
            <CardContent className="p-6">
              <p className="text-red-400">Error: {error}</p>
              <Button onClick={loadData} className="mt-4">Retry</Button>
            </CardContent>
          </Card>
        </PageContainer>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <Header 
        title="Deposit"
        subtitle="Receive ETH to your wallet"
        actions={
          <Button onClick={() => loadData()} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      />
      
      <PageContainer>
        <div className="space-y-6 max-w-4xl animate-stagger">
          {/* Deposit Address Card */}
          <Card>
            <CardHeader>
              <CardTitle>Your Deposit Address</CardTitle>
              <CardDescription>
                Send ETH to this address on Sepolia testnet
              </CardDescription>
            </CardHeader>
            <CardContent>
              {wallet ? (
                <div className="flex items-start gap-6">
                  {/* QR Code Placeholder */}
                  <div className="flex h-40 w-40 items-center justify-center rounded-xl bg-white p-3">
                    <div className="flex h-full w-full items-center justify-center border-2 border-dashed border-surface-300 rounded-lg">
                      <QrCode className="h-16 w-16 text-surface-400" />
                    </div>
                  </div>
                  
                  <div className="flex-1 space-y-4">
                    <div>
                      <p className="text-sm text-surface-500 mb-1">Address</p>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 p-3 rounded-lg bg-surface-800 font-mono text-sm text-surface-200 break-all">
                          {wallet.address}
                        </code>
                        <Button 
                          variant="outline" 
                          size="icon"
                          onClick={() => wallet.address && handleCopy(wallet.address)}
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                        {wallet.address && (
                          <a 
                            href={getExplorerLink('address', wallet.address)}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <Button variant="outline" size="icon">
                              <ExternalLink className="h-4 w-4" />
                            </Button>
                          </a>
                        )}
                      </div>
                    </div>
                    
                    <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/20">
                      <p className="text-sm text-amber-400">
                        <strong>Important:</strong> Only send ETH on the Sepolia testnet. 
                        Deposits require admin approval before being credited to your balance.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-surface-400 mb-4">No wallet found. Create a wallet first.</p>
                  <Button>Create Wallet</Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Deposit History */}
          <Card>
            <CardHeader>
              <CardTitle>Deposit History</CardTitle>
              <CardDescription>Your recent deposits</CardDescription>
            </CardHeader>
            <CardContent>
              {deposits.length > 0 ? (
                <div className="space-y-3">
                  {deposits.map((deposit) => (
                    <div key={deposit.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
                          <ArrowDownLeft className="h-5 w-5" />
                        </div>
                        <div>
                          <p className="font-mono text-sm text-surface-200">
                            From: {formatAddress(deposit.from_address)}
                          </p>
                          <p className="text-sm text-surface-500">
                            {formatRelativeTime(deposit.detected_at)} · Tx: {formatAddress(deposit.tx_hash)}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-surface-200">+{formatEth(deposit.amount)} ETH</p>
                        <StatusBadge status={deposit.status} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-surface-500">
                  No deposits yet
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </PageContainer>
    </div>
  );
}
