// Centralized frontend configuration
// HARDCODED for production - no build-time variables

// Use undefined instead of empty string to force axios relative URL behavior
const API_BASE = undefined as unknown as string;

// Construct WebSocket base from current page location
const WS_BASE = typeof window !== 'undefined' 
  ? window.location.protocol.replace('http', 'ws') + '//' + window.location.host 
  : '';

// Debug logging
console.log('[CONFIG] API_BASE:', API_BASE, 'WS_BASE:', WS_BASE);

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
    if (!API_BASE) {
      // Return relative URL when API_BASE is undefined
      return path.startsWith('/') ? path : `/${path}`;
    }
    const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${base}${p}`;
  }
};

export default APP_CONFIG;
