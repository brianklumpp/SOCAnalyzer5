import { APP_CONFIG } from '../config';

// Native fetch-based API client (no axios)
// This avoids any axios URL resolution issues

class FetchClient {
  private baseURL: string;
  private timeout: number;

  constructor(baseURL: string = '', timeout: number = 120000) {
    this.baseURL = baseURL;
    this.timeout = timeout;
    console.log('[FETCH CLIENT] Initialized with baseURL:', baseURL || '(empty - relative URLs)');
  }

  private buildURL(url: string, params?: Record<string, any>): string {
    // Always use relative URLs - let nginx handle proxying
    const path = url.startsWith('/') ? url : `/${url}`;
    
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value));
        }
      });
      const queryString = searchParams.toString();
      return queryString ? `${path}?${queryString}` : path;
    }
    
    return path;
  }

  private async request(method: string, url: string, options: any = {}) {
    const { params, data, ...fetchOptions } = options;
    const fullURL = this.buildURL(url, params);
    
    console.log('[FETCH REQUEST]', method, fullURL);

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(fetchOptions.headers || {}),
    };

    if (currentAccessToken) {
      headers['Authorization'] = `Bearer ${currentAccessToken}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(fullURL, {
        method,
        headers,
        body: data ? JSON.stringify(data) : undefined,
        signal: controller.signal,
        ...fetchOptions,
      });

      clearTimeout(timeoutId);

      if (response.status === 401 && !fetchOptions._retry) {
        // Handle token refresh
        if (refreshTokenCallback) {
          const success = await refreshTokenCallback();
          if (success) {
            return this.request(method, url, { ...options, _retry: true });
          }
        }
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
      }

      if (!response.ok) {
        const error: any = new Error(`HTTP ${response.status}: ${response.statusText}`);
        error.response = {
          status: response.status,
          statusText: response.statusText,
          data: await response.json().catch(() => ({})),
        };
        throw error;
      }

      const responseData = await response.json();
      return { data: responseData, status: response.status, statusText: response.statusText };
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        throw new Error('Request timeout');
      }
      throw error;
    }
  }

  get(url: string, config?: any) {
    return this.request('GET', url, config);
  }

  post(url: string, data?: any, config?: any) {
    return this.request('POST', url, { ...config, data });
  }

  put(url: string, data?: any, config?: any) {
    return this.request('PUT', url, { ...config, data });
  }

  patch(url: string, data?: any, config?: any) {
    return this.request('PATCH', url, { ...config, data });
  }

  delete(url: string, config?: any) {
    return this.request('DELETE', url, config);
  }
}

export const api = new FetchClient(APP_CONFIG.API_BASE);

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
