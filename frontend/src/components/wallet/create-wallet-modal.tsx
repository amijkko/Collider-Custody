'use client';

import * as React from 'react';
import { Wallet, Shield, Key, Check, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useToastHelpers } from '@/hooks/use-toast';
import { walletsApi } from '@/lib/api';
import { cn } from '@/lib/utils';

interface CreateWalletModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

type Step = 'type' | 'password' | 'keygen' | 'complete';

export function CreateWalletModal({ open, onOpenChange, onSuccess }: CreateWalletModalProps) {
  const [step, setStep] = React.useState<Step>('type');
  const [walletType, setWalletType] = React.useState<'MPC_TECDSA' | 'DEV_SIGNER'>('MPC_TECDSA');
  const [password, setPassword] = React.useState('');
  const [confirmPassword, setConfirmPassword] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(false);
  const [keygenProgress, setKeygenProgress] = React.useState(0);
  const [createdWallet, setCreatedWallet] = React.useState<any>(null);
  const toast = useToastHelpers();

  const handleReset = () => {
    setStep('type');
    setWalletType('MPC_TECDSA');
    setPassword('');
    setConfirmPassword('');
    setKeygenProgress(0);
    setCreatedWallet(null);
  };

  const handleClose = () => {
    handleReset();
    onOpenChange(false);
  };

  const handleCreateWallet = async () => {
    if (walletType === 'MPC_TECDSA') {
      if (password.length < 12) {
        toast.error('Password too short', 'Use at least 12 characters');
        return;
      }
      if (password !== confirmPassword) {
        toast.error('Passwords do not match');
        return;
      }
    }

    setIsLoading(true);
    setStep('keygen');

    try {
      // Simulate keygen progress for demo
      const progressInterval = setInterval(() => {
        setKeygenProgress((prev) => Math.min(prev + 10, 90));
      }, 300);

      // Create wallet via API
      const response = walletType === 'MPC_TECDSA' 
        ? await walletsApi.createMPC({
            wallet_type: 'RETAIL',
            subject_id: `user-wallet-${Date.now()}`,
            mpc_threshold_t: 2,
            mpc_total_n: 2, // 2-of-2 for demo (user + bank)
          })
        : await walletsApi.create({
            wallet_type: 'RETAIL',
            subject_id: `user-wallet-${Date.now()}`,
            custody_backend: 'DEV_SIGNER',
          });

      clearInterval(progressInterval);
      setKeygenProgress(100);
      setCreatedWallet(response.data);

      // In real app: encrypt and store user share in IndexedDB
      // await encryptAndStoreShare(userShare, password, response.data.id, response.data.mpc_keyset_id);

      setTimeout(() => {
        setStep('complete');
        toast.success('Wallet created!', 'Your MPC wallet is ready');
      }, 500);

    } catch (error) {
      toast.error('Failed to create wallet', error instanceof Error ? error.message : 'Please try again');
      setStep('password');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        {step === 'type' && (
          <>
            <DialogHeader>
              <DialogTitle>Create Wallet</DialogTitle>
              <DialogDescription>
                Choose how you want to secure your wallet
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-3 py-4">
              <button
                onClick={() => setWalletType('MPC_TECDSA')}
                className={cn(
                  'w-full p-4 rounded-lg border text-left transition-all',
                  walletType === 'MPC_TECDSA'
                    ? 'border-brand-500 bg-brand-500/10'
                    : 'border-surface-700 hover:border-surface-600'
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-lg',
                    walletType === 'MPC_TECDSA' ? 'bg-brand-500 text-white' : 'bg-surface-700 text-surface-400'
                  )}>
                    <Shield className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="font-medium text-surface-100">MPC Wallet (Recommended)</p>
                    <p className="text-sm text-surface-400">
                      2-of-2 threshold signing. No single point of failure.
                    </p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => setWalletType('DEV_SIGNER')}
                className={cn(
                  'w-full p-4 rounded-lg border text-left transition-all',
                  walletType === 'DEV_SIGNER'
                    ? 'border-brand-500 bg-brand-500/10'
                    : 'border-surface-700 hover:border-surface-600'
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-lg',
                    walletType === 'DEV_SIGNER' ? 'bg-brand-500 text-white' : 'bg-surface-700 text-surface-400'
                  )}>
                    <Key className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="font-medium text-surface-100">Standard Wallet (Dev)</p>
                    <p className="text-sm text-surface-400">
                      Server-side key. For testing only.
                    </p>
                  </div>
                </div>
              </button>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>Cancel</Button>
              <Button onClick={() => setStep(walletType === 'MPC_TECDSA' ? 'password' : 'keygen')}>
                Continue
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'password' && (
          <>
            <DialogHeader>
              <DialogTitle>Secure Your Key</DialogTitle>
              <DialogDescription>
                Create a password to encrypt your signing key. This password never leaves your device.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <Input
                label="Password"
                type="password"
                placeholder="Create a strong password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                hint="At least 12 characters with mixed case, numbers, and symbols"
              />
              <Input
                label="Confirm Password"
                type="password"
                placeholder="Confirm your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                error={confirmPassword && password !== confirmPassword ? 'Passwords do not match' : undefined}
              />
              
              <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/20">
                <p className="text-sm text-amber-400">
                  ⚠️ <strong>Important:</strong> If you lose this password, you won't be able to sign transactions. 
                  There is no recovery option.
                </p>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setStep('type')}>Back</Button>
              <Button 
                onClick={handleCreateWallet}
                disabled={!password || password !== confirmPassword || password.length < 12}
              >
                Create Wallet
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'keygen' && (
          <>
            <DialogHeader>
              <DialogTitle>Creating Your Wallet</DialogTitle>
              <DialogDescription>
                {walletType === 'MPC_TECDSA' 
                  ? 'Generating distributed key shares...'
                  : 'Generating your wallet...'}
              </DialogDescription>
            </DialogHeader>

            <div className="py-8">
              <div className="flex flex-col items-center gap-4">
                <div className="relative h-24 w-24">
                  <svg className="h-24 w-24 transform -rotate-90">
                    <circle
                      className="text-surface-700"
                      strokeWidth="6"
                      stroke="currentColor"
                      fill="transparent"
                      r="42"
                      cx="48"
                      cy="48"
                    />
                    <circle
                      className="text-brand-500 transition-all duration-300"
                      strokeWidth="6"
                      strokeDasharray={264}
                      strokeDashoffset={264 - (264 * keygenProgress) / 100}
                      strokeLinecap="round"
                      stroke="currentColor"
                      fill="transparent"
                      r="42"
                      cx="48"
                      cy="48"
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-brand-400" />
                  </div>
                </div>
                <p className="text-surface-400">{keygenProgress}%</p>
                {walletType === 'MPC_TECDSA' && (
                  <div className="text-center text-sm text-surface-500">
                    <p>DKG Protocol in progress</p>
                    <p>Your key share is being generated locally</p>
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        {step === 'complete' && createdWallet && (
          <>
            <DialogHeader>
              <DialogTitle>Wallet Created!</DialogTitle>
              <DialogDescription>
                Your {walletType === 'MPC_TECDSA' ? 'MPC' : ''} wallet is ready to use
              </DialogDescription>
            </DialogHeader>

            <div className="py-6">
              <div className="flex flex-col items-center gap-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                  <Check className="h-8 w-8" />
                </div>
                
                <div className="text-center">
                  <p className="text-sm text-surface-400 mb-1">Wallet Address</p>
                  <p className="font-mono text-surface-100 break-all">
                    {createdWallet.address}
                  </p>
                </div>

                {walletType === 'MPC_TECDSA' && (
                  <div className="w-full p-4 rounded-lg bg-surface-800/50 border border-surface-700">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-surface-400">Type</span>
                      <span className="text-surface-200">MPC 2-of-2 Threshold</span>
                    </div>
                    <div className="flex items-center justify-between text-sm mt-2">
                      <span className="text-surface-400">Security</span>
                      <span className="text-emerald-400">User + Bank share required</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <DialogFooter>
              <Button onClick={() => { handleClose(); onSuccess?.(); }}>
                Done
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

