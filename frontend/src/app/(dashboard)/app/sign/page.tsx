'use client';

import * as React from 'react';
import { Key, RefreshCw, Check, AlertCircle, Loader2 } from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/badge';
import { useToastHelpers } from '@/hooks/use-toast';
import { txRequestsApi } from '@/lib/api';
import { formatAddress, formatEth, formatRelativeTime } from '@/lib/utils';
import { SignTransactionModal } from '@/components/mpc/sign-transaction-modal';
import { WithdrawRequest } from '@/types';

interface SigningData {
  tx_request_id: string;
  wallet_id: string;
  keyset_id: string | null;
  message_hash: string;
  to_address: string;
  amount: string;
  status: string;
}

export default function SignPage() {
  const toast = useToastHelpers();
  const [pendingTx, setPendingTx] = React.useState<WithdrawRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [selectedTx, setSelectedTx] = React.useState<WithdrawRequest | null>(null);
  const [signingData, setSigningData] = React.useState<SigningData | null>(null);
  const [isLoadingSigningData, setIsLoadingSigningData] = React.useState(false);
  const [showSigningModal, setShowSigningModal] = React.useState(false);

  const loadData = React.useCallback(async () => {
    try {
      const txRes = await txRequestsApi.list();
      // Filter for transactions requiring user signature (SIGN_PENDING = MPC tx awaiting user)
      const pending = txRes.data.filter(tx => tx.status === 'SIGN_PENDING');
      setPendingTx(pending);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSignClick = async (tx: WithdrawRequest) => {
    setSelectedTx(tx);
    setIsLoadingSigningData(true);

    try {
      const response = await txRequestsApi.getSigningData(tx.id);
      setSigningData(response.data);
      setShowSigningModal(true);
    } catch (error) {
      console.error('Failed to get signing data:', error);
      toast.error('Failed to load signing data', error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setIsLoadingSigningData(false);
    }
  };

  const handleSigningSuccess = async (signature: string) => {
    console.log('Signing successful:', signature);

    // TODO: Need to finalize transaction on backend
    // Currently WebSocket signing completes but doesn't save to DB
    // Temporarily disabled REST API call until backend finalization is implemented
    /*
    if (selectedTx) {
      try {
        await txRequestsApi.sign(selectedTx.id);
        toast.success('Transaction signed!', 'Your withdrawal is being processed');
      } catch (error) {
        console.log('Finalization call (expected to handle broadcast):', error);
      }
    }
    */

    toast.success('Transaction signed!', 'MPC signature: ' + signature.slice(0, 20) + '...');

    setShowSigningModal(false);
    setSelectedTx(null);
    setSigningData(null);
    loadData();
  };

  const handleModalClose = (open: boolean) => {
    if (!open) {
      setShowSigningModal(false);
      setSelectedTx(null);
      setSigningData(null);
    }
  };

  return (
    <>
      <Header
        title="Sign Transactions"
        subtitle="Pending transactions requiring your signature"
        actions={
          <Button onClick={() => loadData()} variant="ghost" size="icon">
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      />

      <PageContainer>
        <div className="max-w-4xl animate-stagger">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Key className="h-5 w-5 text-amber-400" />
                Pending Signatures
              </CardTitle>
              <CardDescription>
                Transactions approved by admin that need your signature
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-t-2 border-b-2 border-brand-500"></div>
                </div>
              ) : pendingTx.length > 0 ? (
                <div className="space-y-3">
                  {pendingTx.map((tx) => (
                    <div key={tx.id} className="flex items-center justify-between p-4 rounded-lg bg-surface-800/50 border border-surface-700">
                      <div className="flex items-center gap-4">
                        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400">
                          <Key className="h-6 w-6" />
                        </div>
                        <div>
                          <p className="font-medium text-surface-200">
                            Withdraw to {formatAddress(tx.to_address)}
                          </p>
                          <p className="text-sm text-surface-500">
                            {formatRelativeTime(tx.created_at)} · {tx.approvals.length}/{tx.required_approvals} approvals
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="font-mono text-surface-200">{formatEth(tx.amount)} ETH</p>
                          <StatusBadge status={tx.status} />
                        </div>
                        <Button
                          onClick={() => handleSignClick(tx)}
                          disabled={isLoadingSigningData && selectedTx?.id === tx.id}
                        >
                          {isLoadingSigningData && selectedTx?.id === tx.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            'Sign'
                          )}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 mx-auto mb-4">
                    <Check className="h-8 w-8" />
                  </div>
                  <p className="text-surface-300 font-medium">No pending signatures</p>
                  <p className="text-sm text-surface-500 mt-1">
                    All transactions have been signed
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Info Card */}
          <Card className="mt-6">
            <CardContent className="p-6">
              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400 flex-shrink-0">
                  <AlertCircle className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="font-medium text-surface-200 mb-1">How MPC Signing Works</h4>
                  <p className="text-sm text-surface-400">
                    Your wallet uses MPC (Multi-Party Computation) for security. To sign a transaction,
                    your encrypted key share is decrypted locally using your password, then participates
                    in a 2-of-2 signing protocol with the bank's key share. The full private key is never
                    assembled — only partial signatures are computed and combined.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </PageContainer>

      {/* MPC Signing Modal */}
      {selectedTx && signingData && (
        <SignTransactionModal
          open={showSigningModal}
          onOpenChange={handleModalClose}
          transaction={{
            id: selectedTx.id,
            walletId: signingData.wallet_id,
            mpcKeysetId: signingData.keyset_id,
            toAddress: selectedTx.to_address,
            amount: formatEth(selectedTx.amount),
            status: selectedTx.status,
          }}
          messageHash={signingData.message_hash}
          onSuccess={handleSigningSuccess}
        />
      )}
    </>
  );
}
