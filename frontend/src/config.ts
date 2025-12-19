// Centralized frontend configuration
// Uses Vite define constant injected at build time

declare const __API_BASE__: string;

// Use the build-time constant defined in vite.config.ts
const API_BASE = typeof __API_BASE__ !== 'undefined' ? __API_BASE__ : '';

// Construct WebSocket base from API_BASE or current location
const WS_BASE = API_BASE 
  ? API_BASE.replace(/^http/, 'ws')
  : (typeof window !== 'undefined' 
      ? window.location.protocol.replace('http', 'ws') + '//' + window.location.host 
      : '');

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
