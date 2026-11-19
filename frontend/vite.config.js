import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server proxies /api to FastAPI, so the default API base is "/api".
// Set VITE_API_BASE_URL (see .env.example) to target another backend directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
