import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// GitHub Pages project site only. Dev, tests, and a plain `vite build` stay at /.
// Read through globalThis so this file typechecks without @types/node.
const pagesBase =
  (globalThis as { process?: { env?: { PAGES_BASE?: string } } }).process?.env?.PAGES_BASE || "/";

export default defineConfig({
  base: pagesBase,
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
  },
  test: {
    environment: "happy-dom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
});
