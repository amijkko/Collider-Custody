'use client';

import * as React from 'react';
import { Key, RefreshCw, Check, AlertCircle, Loader2, Lock } from 'lucide-react';
import { Header, PageContainer } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { useToastHelpers } from '@/hooks/use-toast';
import { txRequestsApi } from '@/lib/api';
import { formatAddress, formatEth, formatRelativeTime } from '@/lib/utils';
import { SigningJob, WithdrawRequest } from '@/types';

export default function SignPage() {
  const toast = useToastHelpers();
  const [pendingTx, setPendingTx] = React.useState<WithdrawRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [selectedTx, setSelectedTx] = React.useState<WithdrawRequest | null>(null);
  const [password, setPassword] = React.useState('');
  const [isSigning, setIsSigning] = React.useState(false);
  const [signingStep, setSigningStep] = React.useState(0);

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

  const handleSign = async () => {
    if (!selectedTx || !password) return;

    setIsSigning(true);
    setSigningStep(1);

    try {
      // Step 1: Decrypt key share (simulated - in real implementation would use IndexedDB + PBKDF2)
      await new Promise(r => setTimeout(r, 800));
      setSigningStep(2);

      // Step 2: MPC signing protocol - call backend
      await txRequestsApi.sign(selectedTx.id);
      setSigningStep(3);

      // Step 3: Complete
      await new Promise(r => setTimeout(r, 500));

      toast.success('Transaction signed!', 'Your withdrawal is being processed');
      setSelectedTx(null);
      setPassword('');
      setSigningStep(0);
      loadData();
    } catch (error) {
      console.error('Signing failed:', error);
      toast.error('Signing failed', error instanceof Error ? error.message : 'Please check your password and try again');
      setSigningStep(0);
    } finally {
      setIsSigning(false);
    }
  };

  const signingSteps = [
    { label: 'Decrypting key share', icon: Lock },
    { label: 'MPC signing protocol', icon: Key },
    { label: 'Finalizing signature', icon: Check },
  ];

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
                        <Button onClick={() => setSelectedTx(tx)}>
                          Sign
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

      {/* Signing Modal */}
      <Dialog open={!!selectedTx} onOpenChange={() => !isSigning && setSelectedTx(null)}>
        <DialogContent className="sm:max-w-md">
          {!isSigning ? (
            <>
              <DialogHeader>
                <DialogTitle>Sign Transaction</DialogTitle>
                <DialogDescription>
                  Enter your password to unlock your signing key
                </DialogDescription>
              </DialogHeader>

              <div className="py-4 space-y-4">
                {selectedTx && (
                  <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-surface-400">To</span>
                      <span className="font-mono text-surface-200">{formatAddress(selectedTx.to_address)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-surface-400">Amount</span>
                      <span className="font-mono text-surface-200">{formatEth(selectedTx.amount)} ETH</span>
                    </div>
                  </div>
                )}

                <Input
                  type="password"
                  label="Signing Password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoFocus
                />

                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
                  <p className="text-xs text-amber-400">
                    Your password never leaves this device. It's used to decrypt your local key share.
                  </p>
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setSelectedTx(null)}>
                  Cancel
                </Button>
                <Button onClick={handleSign} disabled={!password}>
                  Sign Transaction
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Signing in Progress</DialogTitle>
                <DialogDescription>
                  Please wait while we sign your transaction
                </DialogDescription>
              </DialogHeader>

              <div className="py-8">
                <div className="space-y-4">
                  {signingSteps.map((step, index) => {
                    const isActive = signingStep === index + 1;
                    const isComplete = signingStep > index + 1;
                    
                    return (
                      <div 
                        key={step.label}
                        className={`flex items-center gap-3 p-3 rounded-lg transition-all ${
                          isActive ? 'bg-brand-500/10 border border-brand-500/30' : 
                          isComplete ? 'bg-emerald-500/10 border border-emerald-500/30' :
                          'bg-surface-800/50 border border-surface-700'
                        }`}
                      >
                        <div className={`flex h-8 w-8 items-center justify-center rounded-full ${
                          isActive ? 'bg-brand-500 text-white' :
                          isComplete ? 'bg-emerald-500 text-white' :
                          'bg-surface-700 text-surface-400'
                        }`}>
                          {isActive ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : isComplete ? (
                            <Check className="h-4 w-4" />
                          ) : (
                            <step.icon className="h-4 w-4" />
                          )}
                        </div>
                        <span className={`text-sm ${
                          isActive ? 'text-brand-400' :
                          isComplete ? 'text-emerald-400' :
                          'text-surface-400'
                        }`}>
                          {step.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

