import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The browser never holds an API key: the dev proxy adds it on the way to FastAPI.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "KAIROS_");
  const target = env.KAIROS_API_URL ?? "http://localhost:8000";
  const apiKey = env.KAIROS_WEB_API_KEY ?? "dev-key";
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5188,
      proxy: {
        "/v1": {
          target,
          changeOrigin: true,
          headers: { "X-API-Key": apiKey },
        },
      },
    },
  };
});
