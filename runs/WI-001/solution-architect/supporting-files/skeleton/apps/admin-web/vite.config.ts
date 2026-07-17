import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/admin/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:4010",
      "/healthz": "http://127.0.0.1:4010"
    }
  }
});
