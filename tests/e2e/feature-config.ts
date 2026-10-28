import fs from "node:fs";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/** Resolve the workspace interpreter on both POSIX and Windows checkouts. */
export function defaultPython(root: string) {
  const windows = path.join(root, ".venv", "Scripts", "python.exe");
  return process.platform === "win32" && fs.existsSync(windows)
    ? windows
    : path.join(root, ".venv", "bin", "python");
}

/** Feature galleries use the same candidate-wheel interpreter as conformance. */
export function featureConfig(
  feature: "budget" | "search" | "label" | "compat" | "interaction",
  port: number,
  extraProjects: NonNullable<Parameters<typeof defineConfig>[0]["projects"]> = [],
) {
  const root = path.resolve(import.meta.dirname, "../..");
  const python = process.env.SGC_CONFORMANCE_PYTHON ?? defaultPython(root);
  const serverLog = `server-${feature}.log`;
  return defineConfig({
    metadata: { serverLog },
    testDir: `./${feature}-tests`,
    outputDir: `./test-results/${feature}`,
    workers: 1,
    retries: process.env.CI ? 1 : 0,
    timeout: 90_000,
    forbidOnly: Boolean(process.env.CI),
    failOnFlakyTests: Boolean(process.env.CI),
    globalTeardown: "./global-teardown.ts",
    reporter: [
      ["list"],
      ["html", { outputFolder: `playwright-report/${feature}`, open: "never" }],
      ["junit", { outputFile: `test-results/junit-${feature}.xml` }],
    ],
    use: {
      baseURL: `http://127.0.0.1:${port}`,
      trace: "retain-on-failure",
      screenshot: "only-on-failure",
      video: "retain-on-failure",
    },
    webServer: {
      command: `${JSON.stringify(python)} ${JSON.stringify(path.join(import.meta.dirname, "run_streamlit.py"))}`,
      url: `http://127.0.0.1:${port}/_stcore/health`,
      cwd: root,
      env: {
        ...process.env,
        PYTHONNOUSERSITE: "1",
        SGC_E2E_APP: `${feature}_gallery.py`,
        SGC_E2E_PORT: String(port),
        SGC_E2E_LOG: serverLog,
      },
      reuseExistingServer: false,
      timeout: 30_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    projects: [
      { name: "chromium", use: { ...devices["Desktop Chrome"] } },
      ...extraProjects,
    ],
  });
}
