/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { sourcemap: false, outDir: "dist" },
  server: { host: "127.0.0.1" },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"], exclude: ["e2e/**", "perf/**", "node_modules/**"] },
});
