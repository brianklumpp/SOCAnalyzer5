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
      '/api': {
        target: 'http://backend:8000',  // Use Docker network hostname
        changeOrigin: true,
      },
      '/auth': {
        target: 'http://backend:8000',  // Use Docker network hostname
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://backend:8000',  // Use Docker network hostname
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
