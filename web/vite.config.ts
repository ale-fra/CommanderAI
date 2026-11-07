import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The UI calls the API on the same origin (/api). In development the Vite
// server forwards /api to `commanderai serve` (default http://127.0.0.1:8000).
const apiTarget = process.env.COMMANDERAI_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    chunkSizeWarningLimit: 800,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
