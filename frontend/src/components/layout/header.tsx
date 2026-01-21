'use client';

import * as React from 'react';
import { Bell, Search, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/use-auth';

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function Header({ title, subtitle, actions }: HeaderProps) {
  return (
    <header className="flex h-16 items-center justify-between border-b border-surface-800 bg-surface-950/80 backdrop-blur-sm px-6 sticky top-0 z-40">
      <div>
        <h1 className="text-lg font-semibold text-surface-100">{title}</h1>
        {subtitle && <p className="text-sm text-surface-500">{subtitle}</p>}
      </div>
      
      <div className="flex items-center gap-3">
        {actions}
        
        <button className="relative rounded-lg p-2 text-surface-400 hover:bg-surface-800 hover:text-surface-100 transition-colors">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brand-500"></span>
        </button>
      </div>
    </header>
  );
}

export function PageContainer({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="p-6 bg-grid min-h-full">
        {children}
      </div>
    </div>
  );
}

