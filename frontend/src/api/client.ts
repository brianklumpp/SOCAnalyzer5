import { APP_CONFIG } from '../config';

// Token management (must be defined before FetchClient uses them)
let currentAccessToken: string | null = null;
let refreshTokenCallback: (() => Promise<boolean>) | null = null;

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

    // Prepare headers
    const headers: HeadersInit = {};
    
    // Don't set Content-Type for FormData - browser will set it with boundary
    const isFormData = data instanceof FormData;
    if (!isFormData) {
      headers['Content-Type'] = 'application/json';
    }
    
    // Add custom headers (but don't override Content-Type for FormData)
    if (fetchOptions.headers) {
      Object.entries(fetchOptions.headers).forEach(([key, value]) => {
        if (!(isFormData && key.toLowerCase() === 'content-type')) {
          headers[key] = value;
        }
      });
    }

    if (currentAccessToken) {
      headers['Authorization'] = `Bearer ${currentAccessToken}`;
    }

    // Use timeout from config if provided, otherwise use default
    const timeoutMs = options.timeout || this.timeout;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(fullURL, {
        method,
        headers,
        body: data ? (isFormData ? data : (typeof data === 'string' ? data : JSON.stringify(data))) : undefined,
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

      // Handle different response types
      let responseData;
      if (options.responseType === 'blob') {
        responseData = await response.blob();
      } else {
        responseData = await response.json();
      }
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

export const setAccessToken = (token: string | null) => {
  currentAccessToken = token;
};

export const getAccessToken = (): string | null => {
  return currentAccessToken;
};

export const setRefreshTokenCallback = (callback: () => Promise<boolean>) => {
  refreshTokenCallback = callback;
};

export const api = new FetchClient(APP_CONFIG.API_BASE);

export default api;
