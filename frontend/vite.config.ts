import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const base = process.env.APP_BASE_PATH || "/";
const apiProxy = {
  "/api": {
    target: "http://localhost:8000",
    changeOrigin: true,
  },
};

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 4174,
    proxy: apiProxy,
    allowedHosts: true,
  },
  preview: {
    host: "0.0.0.0",
    port: 4175,
    proxy: apiProxy,
  },
});
