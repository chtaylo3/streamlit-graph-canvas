import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

function shellQuote(value: string) {
  return "'" + value.replaceAll("'", "'\"'\"'") + "'";
}

/** Feature galleries use the same candidate-wheel interpreter as conformance. */
export function featureConfig(feature: "budget" | "search" | "label", port: number) {
  const root = path.resolve(import.meta.dirname, "../..");
  const python = process.env.SGC_CONFORMANCE_PYTHON ?? path.join(root, ".venv/bin/python");
  return defineConfig({
    testDir: `./${feature}-tests`,
    outputDir: `./test-results/${feature}`,
    workers: 1,
    timeout: 90_000,
    forbidOnly: Boolean(process.env.CI),
    failOnFlakyTests: Boolean(process.env.CI),
    reporter: [["list"], ["junit", {outputFile: `test-results/junit-${feature}.xml`}]],
    use: {baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure"},
    webServer: {
      command: `${shellQuote(python)} -m streamlit run ${shellQuote(path.join(root, `tests/e2e/app/${feature}_gallery.py`))} --server.headless=true --server.port=${port} --browser.gatherUsageStats=false`,
      url: `http://127.0.0.1:${port}/_stcore/health`,
      env: {...process.env, PYTHONNOUSERSITE: "1"},
      reuseExistingServer: false,
      timeout: 30_000,
    },
    projects: [{name: "chromium", use: {...devices["Desktop Chrome"]}}],
  });
}
