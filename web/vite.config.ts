import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxies /api/* to the FastAPI backend (see ../api/main.py) so the
    // browser sees same-origin requests during dev — no CORS config needed
    // on the FastAPI side. Run the backend with:
    //   uv run uvicorn api.main:app --reload --port 8000
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
