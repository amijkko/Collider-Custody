'use client';

import * as React from 'react';
import Link from 'next/link';
import { Shield, ArrowRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/hooks/use-auth';
import { useToastHelpers } from '@/hooks/use-toast';

export default function LoginPage() {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(false);
  const { login } = useAuth();
  const toast = useToastHelpers();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await login(username, password);
      toast.success('Welcome back!', 'Login successful');
    } catch (error) {
      toast.error('Login failed', error instanceof Error ? error.message : 'Invalid credentials');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-grid p-4">
      {/* Background effects */}
      <div className="fixed inset-0 bg-gradient-to-br from-brand-950/50 via-surface-950 to-surface-950 -z-10" />
      <div className="fixed top-1/4 left-1/4 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl -z-10" />
      <div className="fixed bottom-1/4 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl -z-10" />

      <Card className="w-full max-w-md glass-panel animate-fade-in">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-brand-500 shadow-lg shadow-brand-500/30">
            <Shield className="h-7 w-7 text-white" />
          </div>
          <CardTitle className="text-2xl">Welcome back</CardTitle>
          <CardDescription>Sign in to Collider Custody</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Username"
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
            />
            <Input
              label="Password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
            <Button type="submit" className="w-full" isLoading={isLoading}>
              Sign in
              <ArrowRight className="h-4 w-4" />
            </Button>
          </form>

          <div className="mt-6 text-center text-sm text-surface-400">
            Don't have an account?{' '}
            <Link href="/register" className="text-brand-400 hover:text-brand-300 font-medium">
              Create account
            </Link>
          </div>

          {/* Demo credentials hint */}
          <div className="mt-6 p-4 rounded-lg bg-surface-800/50 border border-surface-700">
            <p className="text-xs text-surface-400 text-center mb-2">Demo credentials</p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-surface-500">User:</span>
                <code className="ml-1 text-surface-300">demo</code>
              </div>
              <div>
                <span className="text-surface-500">Pass:</span>
                <code className="ml-1 text-surface-300">demo123456</code>
              </div>
              <div>
                <span className="text-surface-500">Admin:</span>
                <code className="ml-1 text-surface-300">admin2</code>
              </div>
              <div>
                <span className="text-surface-500">Pass:</span>
                <code className="ml-1 text-surface-300">admin123456</code>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

