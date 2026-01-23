'use client';

import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-surface-800 text-surface-200',
        primary: 'border-transparent bg-brand-500/10 text-brand-400 border-brand-500/20',
        success: 'border-transparent bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
        warning: 'border-transparent bg-amber-500/10 text-amber-400 border-amber-500/20',
        destructive: 'border-transparent bg-red-500/10 text-red-400 border-red-500/20',
        outline: 'text-surface-300 border-surface-700',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/**
 * Status badge with automatic color selection
 */
function StatusBadge({ status, className }: { status: string; className?: string }) {
  const getVariant = (status: string): VariantProps<typeof badgeVariants>['variant'] => {
    const s = status.toLowerCase();
    if (s.includes('pending') || s.includes('waiting') || s.includes('submitted') || s.includes('eval')) return 'warning';
    if (s.includes('approved') || s.includes('completed') || s.includes('finalized') || s.includes('active') || s.includes('credited') || s.includes('skipped') || s.includes('confirmed')) return 'success';
    if (s.includes('rejected') || s.includes('failed') || s.includes('blocked') || s.includes('expired')) return 'destructive';
    if (s.includes('progress') || s.includes('confirming') || s.includes('broadcast') || s.includes('signed')) return 'primary';
    return 'default';
  };

  const formatStatus = (status: string): string => {
    return status.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
  };

  return (
    <Badge variant={getVariant(status)} className={className}>
      {formatStatus(status)}
    </Badge>
  );
}

export { Badge, StatusBadge, badgeVariants };

