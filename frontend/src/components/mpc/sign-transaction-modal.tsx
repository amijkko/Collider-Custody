'use client';

import * as React from 'react';
import { X, Key, Loader2, CheckCircle, AlertCircle, Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { createMPCClient, hasShare } from '@/lib/mpc';
import { useToastHelpers } from '@/hooks/use-toast';
import { formatAddress, formatEth } from '@/lib/utils';

interface Transaction {
  id: string;
  walletId: string;
  toAddress: string;
  amount: string;
  status: string;
}

interface SignTransactionModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  transaction: Transaction;
  messageHash: string;
  onSuccess: (signature: string) => void;
}

type Step = 'password' | 'signing' | 'success' | 'error';

export function SignTransactionModal({
  open,
  onOpenChange,
  transaction,
  messageHash,
  onSuccess,
}: SignTransactionModalProps) {
  const toast = useToastHelpers();
  const [step, setStep] = React.useState<Step>('password');
  const [password, setPassword] = React.useState('');
  const [progress, setProgress] = React.useState('');
  const [progressRound, setProgressRound] = React.useState(0);
  const [totalRounds, setTotalRounds] = React.useState(8);
  const [signature, setSignature] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [hasLocalShare, setHasLocalShare] = React.useState<boolean | null>(null);

  // Check if we have a share for this wallet
  React.useEffect(() => {
    if (open && transaction.walletId) {
      hasShare(transaction.walletId).then(setHasLocalShare);
    }
  }, [open, transaction.walletId]);

  // Reset state when modal opens
  React.useEffect(() => {
    if (open) {
      setStep('password');
      setPassword('');
      setProgress('');
      setProgressRound(0);
      setSignature(null);
      setError(null);
    }
  }, [open]);

  const handleSign = async () => {
    if (!password) {
      return;
    }

    setStep('signing');
    setError(null);

    try {
      const client = createMPCClient({
        onProgress: (message, round, total) => {
          setProgress(message);
          setProgressRound(round);
          setTotalRounds(total);
        },
        onError: (err) => {
          setError(err.message);
          setStep('error');
        },
      });

      const result = await client.signTransaction(
        transaction.walletId,
        transaction.id,
        messageHash,
        password
      );

      setSignature(result.fullSignature);
      setStep('success');

      toast.success('Transaction Signed', 'Broadcasting to network...');

      onSuccess(result.fullSignature);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Signing failed';
      setError(message);
      setStep('error');

      if (message.includes('Invalid password')) {
        toast.error('Wrong Password', 'Please check your password and try again');
      } else {
        toast.error('Signing Failed', message);
      }
    }
  };

  const handleClose = () => {
    if (step === 'signing') {
      return;
    }
    onOpenChange(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md rounded-2xl border border-surface-700 bg-surface-900 p-6 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10">
              <Key className="h-5 w-5 text-amber-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-surface-100">
                Sign Transaction
              </h2>
              <p className="text-sm text-surface-400">
                MPC Threshold Signature
              </p>
            </div>
          </div>
          {step !== 'signing' && (
            <button
              onClick={handleClose}
              className="text-surface-400 hover:text-surface-200 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Transaction Details */}
        <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700 mb-4">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-surface-400">To</span>
              <span className="font-mono text-surface-200">
                {formatAddress(transaction.toAddress)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-surface-400">Amount</span>
              <span className="font-mono text-surface-200">
                {transaction.amount} ETH
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-surface-400">Status</span>
              <span className="text-amber-400">{transaction.status}</span>
            </div>
          </div>
        </div>

        {/* Content */}
        {hasLocalShare === false && (
          <div className="py-6 text-center space-y-4">
            <div className="flex justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10">
                <Lock className="h-8 w-8 text-red-400" />
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold text-surface-100">
                No Signing Key Found
              </p>
              <p className="text-sm text-surface-400 mt-2">
                This browser doesn't have the signing key for this wallet.
                You can only sign from the device where you created the wallet.
              </p>
            </div>
            <Button onClick={() => onOpenChange(false)} className="w-full">
              Close
            </Button>
          </div>
        )}

        {hasLocalShare !== false && step === 'password' && (
          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700">
              <div className="flex items-start gap-2">
                <Lock className="h-4 w-4 text-surface-400 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-surface-400">
                  Enter your password to unlock your signing key and authorize
                  this transaction.
                </p>
              </div>
            </div>

            <Input
              type="password"
              label="Password"
              placeholder="Enter your wallet password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && password) {
                  handleSign();
                }
              }}
              autoFocus
            />

            <Button
              onClick={handleSign}
              className="w-full"
              disabled={!password}
            >
              Sign & Broadcast
            </Button>
          </div>
        )}

        {step === 'signing' && (
          <div className="py-8 text-center space-y-4">
            <div className="flex justify-center">
              <Loader2 className="h-12 w-12 text-brand-400 animate-spin" />
            </div>
            <div>
              <p className="text-surface-200 font-medium">{progress}</p>
              <p className="text-sm text-surface-400 mt-1">
                Round {progressRound} of {totalRounds}
              </p>
            </div>
            <div className="w-full bg-surface-800 rounded-full h-2">
              <div
                className="bg-brand-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${(progressRound / totalRounds) * 100}%` }}
              />
            </div>
            <p className="text-xs text-surface-500">
              Do not close this window. Your browser is participating in
              threshold signing.
            </p>
          </div>
        )}

        {step === 'success' && (
          <div className="py-6 text-center space-y-4">
            <div className="flex justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10">
                <CheckCircle className="h-8 w-8 text-emerald-400" />
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold text-surface-100">
                Transaction Signed!
              </p>
              <p className="text-sm text-surface-400 mt-1">
                Broadcasting to Ethereum network...
              </p>
            </div>
            <Button onClick={() => onOpenChange(false)} className="w-full">
              Done
            </Button>
          </div>
        )}

        {step === 'error' && (
          <div className="py-6 text-center space-y-4">
            <div className="flex justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10">
                <AlertCircle className="h-8 w-8 text-red-400" />
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold text-surface-100">
                Signing Failed
              </p>
              <p className="text-sm text-red-400 mt-1">{error}</p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                onClick={() => onOpenChange(false)}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button onClick={() => setStep('password')} className="flex-1">
                Try Again
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

