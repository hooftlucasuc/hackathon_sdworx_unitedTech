import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Poort 5173 = FRONTEND_ORIGIN in de backend-CORS.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
