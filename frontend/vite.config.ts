import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: {
    'process.env': {},  // Polyfill process.env for legacy code
    '__API_BASE__': mode === 'production' ? '""' : '"http://localhost:8000"',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',  // Listen on all interfaces for Docker
    port: 3000,
    proxy: {
      // Proxy all backend API routes to backend container
      // Pattern matches all registered FastAPI routers (see backend/app/main.py)
      // Routes: analyze, report, controls, cuecs, suborgs, deviations, executive_summary,
      //         baseline, config, auth, users, grace, history, settings, framework_criteria,
      //         pdf, docker, test, validate, help, diag, export
      '^/(analyze|report|controls|cuecs|suborgs|deviations|executive_summary|baseline|config|auth|users|grace|history|settings|framework_criteria|pdf|docker|test|validate|help|diag|export)': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      // WebSocket connection for real-time scan progress
      '/ws': {
        target: 'ws://backend:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: false,
    // Code splitting configuration
    rollupOptions: {
      output: {
        manualChunks: undefined, // Let Vite handle chunking automatically
      },
    },
    chunkSizeWarningLimit: 1000,
  },
}));
