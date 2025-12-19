import axios from 'axios';
import { APP_CONFIG } from '../config';

// Centralized Axios client configured from APP_CONFIG
// Force absolute URL construction using window.location.origin to avoid any URL resolution issues
const baseURL = APP_CONFIG.API_BASE || (typeof window !== 'undefined' ? window.location.origin : '');

export const api = axios.create({
  baseURL: baseURL,
  timeout: 120000, // 120 seconds for slow database queries and GPT processing
});

// Debug logging
console.log('[AXIOS] baseURL configured as:', api.defaults.baseURL);

// Function to set access token (called from AuthContext)
let currentAccessToken: string | null = null;

export const setAccessToken = (token: string | null) => {
  currentAccessToken = token;
};

export const getAccessToken = (): string | null => {
  return currentAccessToken;
};

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    console.log('[AXIOS REQUEST]', {
      url: config.url,
      baseURL: config.baseURL,
      fullURL: axios.getUri(config)
    });
    if (currentAccessToken && config.headers) {
      config.headers.Authorization = `Bearer ${currentAccessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle 401 errors
let refreshTokenCallback: (() => Promise<boolean>) | null = null;

export const setRefreshTokenCallback = (callback: () => Promise<boolean>) => {
  refreshTokenCallback = callback;
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If 401 and we haven't already tried to refresh
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (refreshTokenCallback) {
        try {
          const success = await refreshTokenCallback();
          if (success) {
            // Retry original request with new token
            return api(originalRequest);
          }
        } catch (refreshError) {
          // Refresh failed, redirect to login handled by AuthContext
          return Promise.reject(error);
        }
      }

      // No refresh callback or refresh failed, redirect to login
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

export default api;
