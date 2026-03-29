import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target:
          process.env.VITE_API_PROXY_TARGET ??
          `http://127.0.0.1:${process.env.API_PORT ?? "8000"}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@sentiment-tree": path.resolve(__dirname, "../sentiment-tree"),
    },
    dedupe: ["react", "react-dom"],
  },
  optimizeDeps: {
    include: ["framer-motion", "react", "react-dom", "react/jsx-runtime"],
  },
});
