// Centralized frontend configuration
// HARDCODED for production - no build-time variables

// ALWAYS use empty string for production (nginx handles proxying)
const API_BASE = '';

// Construct WebSocket base from current page location
const WS_BASE = typeof window !== 'undefined' 
  ? window.location.protocol.replace('http', 'ws') + '//' + window.location.host 
  : '';

// Debug logging
console.log('[CONFIG] API_BASE:', API_BASE || '(empty string)', 'WS_BASE:', WS_BASE);

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
