import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
