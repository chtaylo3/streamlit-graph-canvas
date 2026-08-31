import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const python = process.env.SGC_CONFORMANCE_PYTHON ?? path.join(root, ".venv", "bin", "python");

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  workers: process.env.CI ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  failOnFlakyTests: Boolean(process.env.CI),
  forbidOnly: Boolean(process.env.CI),
  timeout: 45_000,
  globalTimeout: 15 * 60_000,
  globalTeardown: "./global-teardown.ts",
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }], ["junit", { outputFile: "test-results/junit.xml" }]],
  use: {
    baseURL: "http://127.0.0.1:8513",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    serviceWorkers: "block",
  },
  webServer: {
    command: `${JSON.stringify(python)} ${JSON.stringify(path.join(import.meta.dirname, "run_streamlit.py"))}`,
    url: "http://127.0.0.1:8513/_stcore/health",
    cwd: root,
    env: {
      ...process.env,
      SGC_CONTRIB_SET: process.env.SGC_CONTRIB_SET ?? "stock",
      PYTHONNOUSERSITE: "1",
    },
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
  projects: [{
    name: "chromium",
    use: {
      ...devices["Desktop Chrome"],
      launchOptions: process.env.SGC_CHROMIUM_EXECUTABLE
        ? { executablePath: process.env.SGC_CHROMIUM_EXECUTABLE }
        : undefined,
    },
  }],
});
