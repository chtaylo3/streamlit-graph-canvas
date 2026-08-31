import fs from "node:fs";
import path from "node:path";

export default function globalTeardown() {
  const logPath = path.resolve(import.meta.dirname, "..", "conformance-artifacts", "server.log");
  if (!fs.existsSync(logPath)) throw new Error(`Streamlit server log is missing: ${logPath}`);
  const log = fs.readFileSync(logPath, "utf8");
  const fatalPatterns = [
    /Traceback \(most recent call last\)/,
    /Uncaught app execution/,
    /Component Error/,
  ];
  const match = fatalPatterns.find((pattern) => pattern.test(log));
  if (match) throw new Error(`Streamlit server emitted a fatal signature ${match}:\n${log}`);
}
