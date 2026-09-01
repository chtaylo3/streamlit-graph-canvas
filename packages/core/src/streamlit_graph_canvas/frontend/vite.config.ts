import { readFileSync } from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

function bundledPackage(moduleId: string): { name: string; version: string } | null {
  const normalized = moduleId.replaceAll("\\", "/").split("?", 1)[0];
  const marker = "/node_modules/";
  const markerIndex = normalized.lastIndexOf(marker);
  if (markerIndex < 0) return null;
  const remainder = normalized.slice(markerIndex + marker.length).split("/");
  const packageParts = remainder[0].startsWith("@")
    ? remainder.slice(0, 2)
    : remainder.slice(0, 1);
  const packageRoot = normalized.slice(0, markerIndex + marker.length)
    + packageParts.join("/");
  const metadata = JSON.parse(
    readFileSync(path.join(packageRoot, "package.json"), "utf8"),
  ) as { name: string; version: string };
  return { name: metadata.name, version: metadata.version };
}

function bundledPackageInventory(): Plugin {
  return {
    name: "streamlit-graph-canvas-bundled-package-inventory",
    generateBundle() {
      const packages = new Map<string, { name: string; version: string }>();
      for (const moduleId of this.getModuleIds()) {
        const metadata = bundledPackage(moduleId);
        if (metadata) packages.set(`${metadata.name}@${metadata.version}`, metadata);
      }
      this.emitFile({
        type: "asset",
        fileName: "bundled-packages.json",
        source: `${JSON.stringify({ schema: 1, packages: [...packages.values()].sort((left, right) => left.name.localeCompare(right.name)) }, null, 2)}\n`,
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), bundledPackageInventory()],
  base: "./",
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "build",
    emptyOutDir: true,
    lib: {
      entry: "./src/index.tsx",
      formats: ["es"],
      fileName: "index-[hash]",
    },
    rollupOptions: {
      output: {
        assetFileNames: "index-[hash][extname]",
      },
    },
  },
});
