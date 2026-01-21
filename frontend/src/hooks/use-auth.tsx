'use client';

import * as React from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { authApi, ApiRequestError } from '@/lib/api';
import { User, UserRole } from '@/types';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string, role?: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: UserRole[]) => boolean;
}

const AuthContext = React.createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const router = useRouter();
  const pathname = usePathname();

  // Check auth on mount
  React.useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setIsLoading(false);
        return;
      }

      try {
        const response = await authApi.me();
        setUser(response.data as User);
      } catch (error) {
        localStorage.removeItem('access_token');
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Redirect logic
  React.useEffect(() => {
    if (isLoading) return;

    const isAuthPage = pathname === '/login' || pathname === '/register';
    const isAdminPage = pathname?.startsWith('/admin');

    if (!user && !isAuthPage) {
      router.push('/login');
    } else if (user && isAuthPage) {
      router.push(user.role === 'ADMIN' ? '/admin' : '/app');
    } else if (user && isAdminPage && user.role !== 'ADMIN') {
      router.push('/app');
    }
  }, [user, isLoading, pathname, router]);

  const login = async (username: string, password: string) => {
    try {
      const response = await authApi.login({ username, password });
      localStorage.setItem('access_token', response.data.access_token);

      const userResponse = await authApi.me();
      setUser(userResponse.data as User);
      
      router.push(userResponse.data.role === 'ADMIN' ? '/admin' : '/app');
    } catch (error) {
      if (error instanceof ApiRequestError) {
        throw new Error(error.message);
      }
      throw error;
    }
  };

  const register = async (username: string, email: string, password: string, role?: string) => {
    try {
      await authApi.register({ username, email, password, role });
      // Auto-login after registration
      await login(username, password);
    } catch (error) {
      if (error instanceof ApiRequestError) {
        throw new Error(error.message);
      }
      throw error;
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    setUser(null);
    router.push('/login');
  };

  const hasRole = (...roles: UserRole[]) => {
    if (!user) return false;
    return roles.includes(user.role);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

// HOC for protected routes
export function withAuth<P extends object>(
  Component: React.ComponentType<P>,
  allowedRoles?: UserRole[]
) {
  return function ProtectedComponent(props: P) {
    const { user, isLoading, hasRole } = useAuth();
    const router = useRouter();

    React.useEffect(() => {
      if (!isLoading && !user) {
        router.push('/login');
      } else if (!isLoading && user && allowedRoles && !hasRole(...allowedRoles)) {
        router.push('/app');
      }
    }, [isLoading, user, router]);

    if (isLoading) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-brand-500"></div>
        </div>
      );
    }

    if (!user) return null;
    if (allowedRoles && !hasRole(...allowedRoles)) return null;

    return <Component {...props} />;
  };
}

