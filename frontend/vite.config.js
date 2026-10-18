import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/upload': 'http://127.0.0.1:8000', '/parse': 'http://127.0.0.1:8000', '/execute': 'http://127.0.0.1:8000', '/logs': 'http://127.0.0.1:8000', '/report': 'http://127.0.0.1:8000', '/openapi.json': 'http://127.0.0.1:8000' }
  }
});