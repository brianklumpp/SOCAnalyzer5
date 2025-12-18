// Centralized frontend configuration
// Pulls values from environment variables and provides helpers for URLs

// Frontend runs on port 3000, backend API runs on port 8000
// In production, use empty string (relative URLs) so nginx can proxy
// In development, use localhost:8000 for direct backend access
const API_BASE = import.meta.env.VITE_API_BASE !== undefined 
  ? import.meta.env.VITE_API_BASE 
  : (import.meta.env.MODE === 'production' ? '' : 'http://localhost:8000');
const WS_BASE = import.meta.env.VITE_WS_BASE || API_BASE.replace(/^https?:/i, (proto) => proto.toLowerCase() === 'https:' ? 'wss:' : 'ws:');

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
