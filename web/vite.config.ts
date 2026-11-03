import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

// `npm run dev` hace de proxy al servidor de `clipero app` (siempre 127.0.0.1, no localhost).
const backend = 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [vue()],
  // el build va dentro del paquete (package-data): lo sirve clipero/app/server.py
  build: { outDir: '../clipero/app/static', emptyOutDir: true },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/media': { target: backend, changeOrigin: true },
    },
  },
});
