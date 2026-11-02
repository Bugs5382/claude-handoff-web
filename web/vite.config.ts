import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The built file lands in the template, so installing needs only Python. CI checks it matches the source.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname as string, "src") } },
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: path.resolve(import.meta.dirname as string, "../template/_site/app"),
    emptyOutDir: true,
    sourcemap: false,
    lib: { entry: "src/index.tsx", name: "HandoffSite", formats: ["iife"], fileName: () => "app.js" },
  },
});
