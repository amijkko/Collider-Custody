import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format Ethereum address for display (0x1234...5678)
 */
export function formatAddress(address: string | null | undefined, chars: number = 4): string {
  if (!address) return '—';
  return `${address.slice(0, chars + 2)}...${address.slice(-chars)}`;
}

/**
 * Convert wei to ETH
 */
export function weiToEth(weiAmount: string | number): number {
  const wei = typeof weiAmount === 'string' ? parseFloat(weiAmount) : weiAmount;
  if (isNaN(wei)) return 0;
  return wei / 1e18;
}

/**
 * Format ETH amount with proper decimals (handles both wei and ETH values)
 */
export function formatEth(amount: string | number, decimals: number = 6): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount;
  if (isNaN(num)) return '0';
  
  // If amount looks like wei (> 1e12), convert to ETH
  const ethValue = num > 1e12 ? num / 1e18 : num;
  
  return ethValue.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format USD value
 */
export function formatUsd(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

/**
 * Format date/time for display
 */
export function formatDateTime(dateStr: string | Date): string {
  const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(dateStr: string | Date): string {
  const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return formatDateTime(date);
}

/**
 * Get status color class
 */
export function getStatusColor(status: string): string {
  const statusLower = status.toLowerCase();
  
  if (statusLower.includes('pending') || statusLower.includes('waiting')) {
    return 'status-pending';
  }
  if (statusLower.includes('approved') || statusLower.includes('completed') || statusLower.includes('finalized') || statusLower.includes('credited')) {
    return 'status-approved';
  }
  if (statusLower.includes('rejected') || statusLower.includes('failed') || statusLower.includes('blocked')) {
    return 'status-rejected';
  }
  if (statusLower.includes('processing') || statusLower.includes('progress') || statusLower.includes('confirming') || statusLower.includes('broadcast')) {
    return 'status-processing';
  }
  return 'status-pending';
}

/**
 * Sleep utility
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Copy to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Generate etherscan link for Sepolia
 */
export function getExplorerLink(type: 'tx' | 'address', value: string): string {
  const baseUrl = 'https://sepolia.etherscan.io';
  return `${baseUrl}/${type}/${value}`;
}

/**
 * Truncate string in middle
 */
export function truncateMiddle(str: string, maxLength: number = 20): string {
  if (str.length <= maxLength) return str;
  const half = Math.floor((maxLength - 3) / 2);
  return `${str.slice(0, half)}...${str.slice(-half)}`;
}

/**
 * Validate Ethereum address
 */
export function isValidAddress(address: string): boolean {
  return /^0x[a-fA-F0-9]{40}$/.test(address);
}

/**
 * Validate positive amount
 */
export function isValidAmount(amount: string): boolean {
  const num = parseFloat(amount);
  return !isNaN(num) && num > 0;
}

