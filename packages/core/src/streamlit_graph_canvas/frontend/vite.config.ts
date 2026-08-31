import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "build",
    emptyOutDir: true,
    lib: {
      entry: "./src/index.tsx",
      formats: ["es"],
      fileName: "index-[hash]",
      cssFileName: "index-[hash]",
    },
  },
});

