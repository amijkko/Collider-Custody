'use client';

import * as React from 'react';
import { X, Shield, Key, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { createMPCClient, validatePassword } from '@/lib/mpc';
import { useToastHelpers } from '@/hooks/use-toast';

interface CreateMPCWalletModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  walletId: string;
  onSuccess: (result: { keysetId: string; address: string }) => void;
}

type Step = 'password' | 'creating' | 'success' | 'error';

export function CreateMPCWalletModal({
  open,
  onOpenChange,
  walletId,
  onSuccess,
}: CreateMPCWalletModalProps) {
  const toast = useToastHelpers();
  const [step, setStep] = React.useState<Step>('password');
  const [password, setPassword] = React.useState('');
  const [confirmPassword, setConfirmPassword] = React.useState('');
  const [passwordErrors, setPasswordErrors] = React.useState<string[]>([]);
  const [progress, setProgress] = React.useState('');
  const [progressRound, setProgressRound] = React.useState(0);
  const [totalRounds, setTotalRounds] = React.useState(3);
  const [result, setResult] = React.useState<{ keysetId: string; address: string } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // Reset state when modal opens
  React.useEffect(() => {
    if (open) {
      setStep('password');
      setPassword('');
      setConfirmPassword('');
      setPasswordErrors([]);
      setProgress('');
      setProgressRound(0);
      setResult(null);
      setError(null);
    }
  }, [open]);

  const handlePasswordChange = (value: string) => {
    setPassword(value);
    const validation = validatePassword(value);
    setPasswordErrors(validation.errors);
  };

  const handleCreateWallet = async () => {
    // Validate passwords
    if (password !== confirmPassword) {
      setPasswordErrors(['Passwords do not match']);
      return;
    }

    const validation = validatePassword(password);
    if (!validation.valid) {
      setPasswordErrors(validation.errors);
      return;
    }

    setStep('creating');
    setError(null);

    try {
      const client = createMPCClient({
        wsUrl: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000',
        onProgress: (message: string, round: number, total: number) => {
          setProgress(message);
          setProgressRound(round);
          setTotalRounds(total);
        },
        onError: (err: Error) => {
          setError(err.message);
          setStep('error');
        },
      });

      await client.connect();
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      if (token) {
        await client.authenticate();
      }
      const dkgResult = await client.startDKG(walletId, password);

      setResult({
        keysetId: dkgResult.keysetId,
        address: dkgResult.ethereumAddress,
      });
      setStep('success');

      toast.success(
        'MPC Wallet Created',
        `Address: ${dkgResult.ethereumAddress.slice(0, 10)}...`
      );

      onSuccess({
        keysetId: dkgResult.keysetId,
        address: dkgResult.ethereumAddress,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create wallet';
      setError(message);
      setStep('error');
      toast.error('Wallet Creation Failed', message);
    }
  };

  const handleClose = () => {
    if (step === 'creating') {
      // Don't allow closing during creation
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
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10">
              <Shield className="h-5 w-5 text-brand-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-surface-100">
                Create MPC Wallet
              </h2>
              <p className="text-sm text-surface-400">
                2-of-2 Threshold Signature
              </p>
            </div>
          </div>
          {step !== 'creating' && (
            <button
              onClick={handleClose}
              className="text-surface-400 hover:text-surface-200 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Content */}
        {step === 'password' && (
          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/20">
              <div className="flex items-start gap-2">
                <Key className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-amber-400">
                  <p className="font-medium mb-1">Important: Save your password!</p>
                  <p className="text-amber-400/80">
                    Your password encrypts your signing key. Without it, you cannot
                    sign transactions. We cannot recover it for you.
                  </p>
                </div>
              </div>
            </div>

            <Input
              type="password"
              label="Password"
              placeholder="Enter a strong password"
              value={password}
              onChange={(e) => handlePasswordChange(e.target.value)}
              error={passwordErrors[0]}
            />

            <Input
              type="password"
              label="Confirm Password"
              placeholder="Confirm your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              error={password !== confirmPassword && confirmPassword ? 'Passwords do not match' : undefined}
            />

            {passwordErrors.length > 0 && (
              <div className="text-sm text-red-400 space-y-1">
                {passwordErrors.map((err, i) => (
                  <p key={i}>• {err}</p>
                ))}
              </div>
            )}

            <Button
              onClick={handleCreateWallet}
              className="w-full"
              disabled={!password || !confirmPassword || password !== confirmPassword || passwordErrors.length > 0}
            >
              Create Wallet
            </Button>
          </div>
        )}

        {step === 'creating' && (
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
              Do not close this window. Your browser is participating in secure key generation.
            </p>
          </div>
        )}

        {step === 'success' && result && (
          <div className="py-6 text-center space-y-4">
            <div className="flex justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10">
                <CheckCircle className="h-8 w-8 text-emerald-400" />
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold text-surface-100">
                Wallet Created Successfully!
              </p>
              <p className="text-sm text-surface-400 mt-1">
                Your MPC wallet is ready to use
              </p>
            </div>
            <div className="p-4 rounded-lg bg-surface-800/50 border border-surface-700">
              <p className="text-xs text-surface-400 mb-1">Wallet Address</p>
              <p className="font-mono text-sm text-surface-200 break-all">
                {result.address}
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
                Wallet Creation Failed
              </p>
              <p className="text-sm text-red-400 mt-1">
                {error}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                onClick={() => onOpenChange(false)}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                onClick={() => setStep('password')}
                className="flex-1"
              >
                Try Again
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

