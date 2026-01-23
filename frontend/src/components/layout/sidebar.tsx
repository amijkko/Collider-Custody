'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Wallet,
  ArrowDownLeft,
  ArrowUpRight,
  Shield,
  Users,
  LayoutDashboard,
  LogOut,
  Key,
  FileText,
  Settings,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/hooks/use-auth';

interface NavItem {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  roles?: string[];
}

const clientNavItems: NavItem[] = [
  { title: 'Dashboard', href: '/app', icon: LayoutDashboard },
  { title: 'Deposit', href: '/app/deposit', icon: ArrowDownLeft },
  { title: 'Withdraw', href: '/app/withdraw', icon: ArrowUpRight },
  { title: 'Sign', href: '/app/sign', icon: Key },
];

const adminNavItems: NavItem[] = [
  { title: 'Dashboard', href: '/admin', icon: LayoutDashboard },
  { title: 'Groups', href: '/admin/groups', icon: Users },
  { title: 'Deposits', href: '/admin/deposits', icon: ArrowDownLeft },
  { title: 'Withdrawals', href: '/admin/withdrawals', icon: ArrowUpRight },
  { title: 'Audit', href: '/admin/audit', icon: FileText },
];

export function Sidebar({ isAdmin = false }: { isAdmin?: boolean }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const navItems = isAdmin ? adminNavItems : clientNavItems;

  return (
    <div className="flex h-screen w-64 flex-col border-r border-surface-800 bg-surface-950">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 border-b border-surface-800 px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500">
          <Shield className="h-4 w-4 text-white" />
        </div>
        <span className="font-semibold text-surface-100">Collider</span>
        {isAdmin && (
          <span className="ml-auto rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-400">
            Admin
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-4">
        {navItems.map((item) => {
          const isActive = pathname === item.href || 
            (item.href !== '/app' && item.href !== '/admin' && pathname?.startsWith(item.href));
          
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all',
                isActive
                  ? 'bg-brand-500/10 text-brand-400'
                  : 'text-surface-400 hover:bg-surface-800 hover:text-surface-100'
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.title}
            </Link>
          );
        })}
      </nav>

      {/* User section */}
      <div className="border-t border-surface-800 p-4">
        <div className="flex items-center gap-3 rounded-lg bg-surface-900 p-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500/20 text-brand-400">
            {user?.username?.[0]?.toUpperCase() || 'U'}
          </div>
          <div className="flex-1 truncate">
            <p className="text-sm font-medium text-surface-100 truncate">
              {user?.username}
            </p>
            <p className="text-xs text-surface-500">{user?.role}</p>
          </div>
          <button
            onClick={logout}
            className="rounded-lg p-2 text-surface-400 hover:bg-surface-800 hover:text-surface-100 transition-colors"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

