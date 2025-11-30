import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { apiGet, apiPost } from '../api/client';

interface AuthState {
  authenticated: boolean;
  authMethod: string;
  setupRequired: boolean;
  loading: boolean;
  username: string | null;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>({
    authenticated: false,
    authMethod: 'none',
    setupRequired: false,
    loading: true,
    username: null,
  });

  const checkSession = async () => {
    try {
      const response = await apiGet<{
        authenticated: boolean;
        auth_method: string;
        setup_required: boolean;
        username: string | null;
      }>('/auth/session');

      setAuthState({
        authenticated: response.authenticated,
        authMethod: response.auth_method,
        setupRequired: response.setup_required,
        username: response.username || null,
        loading: false,
      });
    } catch (error) {
      console.error('Failed to check session:', error);
      setAuthState({
        authenticated: false,
        authMethod: 'none',
        setupRequired: true,
        username: null,
        loading: false,
      });
    }
  };

  const login = async (username: string, password: string) => {
    const response = await apiPost<{
      success: boolean;
      message: string;
    }>('/auth/login', {
      username,
      password,
    });

    if (!response.success) {
      throw new Error(response.message || 'Login failed');
    }

    // Re-check session to update auth state
    await checkSession();
  };

  const logout = async () => {
    await apiPost('/auth/logout', {});
    setAuthState({
      authenticated: false,
      authMethod: 'none',
      setupRequired: false,
      username: null,
      loading: false,
    });
  };

  // Check session on mount
  useEffect(() => {
    checkSession();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        ...authState,
        login,
        logout,
        checkSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

