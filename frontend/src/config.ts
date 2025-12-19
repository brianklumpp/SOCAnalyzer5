// Centralized frontend configuration
// Uses runtime detection instead of build-time environment variables
// This avoids issues with Vite env var resolution

// Detect if running in development (Vite dev server on port 5173 or localhost)
const isDev = typeof window !== 'undefined' && 
  (window.location.port === '5173' || window.location.hostname === 'localhost');

// In development: use localhost:8000
// In production: use empty string (relative URLs) for nginx to proxy
const API_BASE = isDev ? 'http://localhost:8000' : '';

// Construct WebSocket base from current page URL in production
const WS_BASE = isDev 
  ? 'ws://localhost:8000'
  : (typeof window !== 'undefined' 
      ? window.location.protocol.replace('http', 'ws') + '//' + window.location.host 
      : '');

// Debug logging
if (typeof window !== 'undefined') {
  console.log('[CONFIG] hostname:', window.location.hostname, 'port:', window.location.port);
  console.log('[CONFIG] isDev:', isDev, 'API_BASE:', API_BASE || '(empty string)');
}

export const APP_CONFIG = {
  API_BASE,
  WS_BASE,
  // Helper to build a WS URL from a path like '/ws'
  wsUrl: (path: string) => {
    const base = WS_BASE.endsWith('/') ? WS_BASE.slice(0, -1) : WS_BASE;
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${base}${p}`;
  },
  // Helper to build an API URL if absolute needed (prefer using the axios client)
  apiUrl: (path: string) => {
    const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${base}${p}`;
  }
};

export default APP_CONFIG;
