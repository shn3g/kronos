import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import process from "node:process";
import { webEngineProxyPlugin } from "./src/engine/webEngineProxy";

const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react(), webEngineProxyPlugin()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    passWithNoTests: true,
  },
});
