'use client';

import * as React from 'react';
import { AuthProvider } from '@/hooks/use-auth';
import { ToastContextProvider, useToast } from '@/hooks/use-toast';
import {
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
  ToastIcon,
} from '@/components/ui/toast';

function ToastRenderer() {
  const { toasts, dismiss } = useToast();

  return (
    <ToastProvider>
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          variant={toast.variant}
          onOpenChange={(open) => !open && dismiss(toast.id)}
        >
          <ToastIcon variant={toast.variant} />
          <div className="flex-1">
            {toast.title && <ToastTitle>{toast.title}</ToastTitle>}
            {toast.description && <ToastDescription>{toast.description}</ToastDescription>}
          </div>
          <ToastClose />
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ToastContextProvider>
      <AuthProvider>
        {children}
        <ToastRenderer />
      </AuthProvider>
    </ToastContextProvider>
  );
}

