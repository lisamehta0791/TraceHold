import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const PORT = process.env.TRACEHOLD_API_PORT || '8000';
const BACKEND = `http://127.0.0.1:${PORT}`;
const HELP = `The TraceHold API is not running on 127.0.0.1:${PORT}. Start it in another terminal: `
  + `cd backend  then  ..\\.venv\\Scripts\\python -m uvicorn app.main:app --port ${PORT}`;

let lastWarn = 0;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        configure: (proxy) => {
          // One readable line (at most once a minute) instead of a stack trace per request,
          // and a JSON answer the website can show to the user.
          proxy.on('error', (_err, _req, res) => {
            if (Date.now() - lastWarn > 60_000) {
              lastWarn = Date.now();
              console.warn(`\n  [TraceHold] ${HELP}\n`);
            }
            const r = res as unknown as { headersSent?: boolean; writeHead?: (c: number, h: Record<string, string>) => void; end?: (b: string) => void };
            if (r && !r.headersSent && r.writeHead && r.end) {
              r.writeHead(503, { 'Content-Type': 'application/json' });
              r.end(JSON.stringify({ detail: HELP }));
            }
          });
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ['recharts'],
        },
      },
    },
  },
});
