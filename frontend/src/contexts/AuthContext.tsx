import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api, setAccessToken as setApiAccessToken, setRefreshTokenCallback } from '../api/client';

interface User {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Initialize: Set up refresh callback and check for existing session
  useEffect(() => {
    // Set refresh callback for API interceptor
    setRefreshTokenCallback(refreshAccessToken);

    const initializeAuth = async () => {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          // Try to refresh access token
          const success = await refreshAccessToken();
          if (success) {
            // Fetch current user
            await fetchCurrentUser();
          }
        } catch (error) {
          console.error('Failed to initialize auth:', error);
          localStorage.removeItem('refresh_token');
        }
      }
      setLoading(false);
    };

    initializeAuth();
  }, []);

  const fetchCurrentUser = async () => {
    try {
      const response = await api.get('/auth/me');
      setUser(response.data);
    } catch (error) {
      console.error('Failed to fetch current user:', error);
      setUser(null);
      setAccessToken(null);
    }
  };

  const login = async (username: string, password: string) => {
    try {
      // OAuth2PasswordRequestForm expects application/x-www-form-urlencoded
      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);

      const response = await api.post('/auth/login', params.toString(), {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      const { access_token, refresh_token, user: userData } = response.data;

      // Store tokens
      setAccessToken(access_token);
      setApiAccessToken(access_token); // Update API client
      localStorage.setItem('refresh_token', refresh_token);
      
      // Store login timestamp for completed scan notifications
      localStorage.setItem('last_login_timestamp', new Date().toISOString());
      
      setUser(userData);
    } catch (error: any) {
      console.error('Login failed:', error);
      throw new Error(error.response?.data?.detail || 'Login failed');
    }
  };

  const logout = async () => {
    try {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken && accessToken) {
        await api.post('/auth/logout', { refresh_token: refreshToken });
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // Clear local state regardless of API call result
      setUser(null);
      setAccessToken(null);
      setApiAccessToken(null); // Clear API client token
      localStorage.removeItem('refresh_token');
    }
  };

  const refreshAccessToken = async (): Promise<boolean> => {
    try {
      const refreshToken = localStorage.getItem('refresh_token');
      if (!refreshToken) {
        return false;
      }

      const response = await api.post('/auth/refresh', { refresh_token: refreshToken });
      const { access_token } = response.data;

      setAccessToken(access_token);
      setApiAccessToken(access_token); // Update API client
      return true;
    } catch (error) {
      console.error('Token refresh failed:', error);
      localStorage.removeItem('refresh_token');
      setAccessToken(null);
      setUser(null);
      return false;
    }
  };

  const value: AuthContextType = {
    user,
    accessToken,
    isAuthenticated: !!user && !!accessToken,
    isAdmin: user?.is_admin || false,
    loading,
    login,
    logout,
    refreshAccessToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
