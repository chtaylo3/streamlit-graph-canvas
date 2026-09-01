import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { FullConfig } from "@playwright/test";

export default function globalTeardown(config: FullConfig) {
  try {
    const logPath = path.resolve(import.meta.dirname, "artifacts", "server.log");
    if (!fs.existsSync(logPath)) throw new Error(`Streamlit server log is missing: ${logPath}`);
    const log = fs.readFileSync(logPath, "utf8");
    const fatalPatterns = [
      /Traceback \(most recent call last\)/,
      /Uncaught app execution/,
      /Component Error/,
    ];
    const match = fatalPatterns.find((pattern) => pattern.test(log));
    if (match) throw new Error(`Streamlit server emitted a fatal signature ${match}:\n${log}`);
  } finally {
    const tlsDirectory = config.metadata.cspTlsDirectory;
    if (typeof tlsDirectory === "string") {
      const resolved = path.resolve(tlsDirectory);
      const temporaryRoot = path.resolve(os.tmpdir());
      if (
        path.dirname(resolved) !== temporaryRoot
        || !path.basename(resolved).startsWith("sgc-csp-tls-")
      ) {
        throw new Error(`Refusing to remove unexpected TLS directory: ${resolved}`);
      }
      fs.rmSync(resolved, { recursive: true, force: true });
    }
  }
}
