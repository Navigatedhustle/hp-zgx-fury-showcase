import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/** Split vendor code so a route only pays for what it uses. */
function vendorChunk(id: string): string | undefined {
  if (!id.includes("node_modules")) return undefined;
  if (id.includes("@dnd-kit")) return "dnd";           // Export only
  if (id.includes("react-router")) return "router";
  if (id.includes("@tanstack")) return "query";
  if (id.includes("@radix-ui") || id.includes("sonner") || id.includes("lucide-react")) return "ui";
  // Library → Graph only (lazy): sigma, graphology and their `events` shim.
  if (/[\\/]node_modules[\\/](sigma|@react-sigma|graphology[^\\/]*|events)[\\/]/.test(id)) return "graph";
  return "vendor";                                      // react, react-dom, scheduler, clsx
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: false } },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 250,
    rollupOptions: { output: { manualChunks: vendorChunk } },
  },
});
