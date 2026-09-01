import { execFileSync } from "node:child_process";
import { createHash, X509Certificate } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

function createEphemeralCertificate(repositoryRoot: string) {
  const repositoryId = createHash("sha256")
    .update(repositoryRoot)
    .digest("hex")
    .slice(0, 12);
  const directory = path.join(os.tmpdir(), `sgc-csp-tls-${repositoryId}`);
  const certificate = path.join(directory, "cert.pem");
  const privateKey = path.join(directory, "key.pem");
  try {
    if (fs.existsSync(certificate) && fs.existsSync(privateKey)) {
      try {
        const existing = new X509Certificate(fs.readFileSync(certificate));
        if (Date.parse(existing.validTo) > Date.now() + 5 * 60_000) {
          const publicKey = existing.publicKey.export({ type: "spki", format: "der" });
          const spkiFingerprint = createHash("sha256")
            .update(publicKey)
            .digest("base64");
          return { certificate, directory, privateKey, spkiFingerprint };
        }
      } catch {
        // Replace partial or malformed output left by an interrupted test run.
      }
    }
    fs.rmSync(directory, { recursive: true, force: true });
    fs.mkdirSync(directory, { mode: 0o700 });
    execFileSync("openssl", [
      "req",
      "-x509",
      "-newkey", "rsa:2048",
      "-sha256",
      "-nodes",
      "-keyout", privateKey,
      "-out", certificate,
      "-days", "1",
      "-subj", "/CN=localhost",
      "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
      "-addext", "basicConstraints=critical,CA:FALSE",
      "-addext", "keyUsage=critical,digitalSignature,keyEncipherment",
      "-addext", "extendedKeyUsage=serverAuth",
    ], { stdio: "pipe" });
    fs.chmodSync(privateKey, 0o600);
    const publicKey = new X509Certificate(fs.readFileSync(certificate))
      .publicKey.export({ type: "spki", format: "der" });
    const spkiFingerprint = createHash("sha256").update(publicKey).digest("base64");
    return { certificate, directory, privateKey, spkiFingerprint };
  } catch (error) {
    fs.rmSync(directory, { recursive: true, force: true });
    throw new Error("OpenSSL could not generate the ephemeral CSP test certificate", {
      cause: error,
    });
  }
}

const root = path.resolve(import.meta.dirname, "../..");
const python = process.env.SGC_CONFORMANCE_PYTHON ?? path.join(root, ".venv", "bin", "python");
const contribSet = process.env.SGC_CONTRIB_SET ?? "stock";
const cspProxy = process.env.SGC_CSP_PROXY === "true";
const port = cspProxy ? 8514 : 8513;
const protocol = cspProxy ? "https" : "http";
const tls = cspProxy ? createEphemeralCertificate(root) : undefined;

export default defineConfig({
  metadata: {
    ...(tls ? { cspTlsDirectory: tls.directory } : {}),
  },
  testDir: "./tests",
  outputDir: `./test-results/${contribSet}`,
  workers: process.env.CI ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  failOnFlakyTests: Boolean(process.env.CI),
  forbidOnly: Boolean(process.env.CI),
  timeout: 45_000,
  globalTimeout: 15 * 60_000,
  globalTeardown: "./global-teardown.ts",
  reporter: [["list"], ["html", { outputFolder: `playwright-report/${contribSet}`, open: "never" }], ["junit", { outputFile: `test-results/junit-${contribSet}.xml` }]],
  use: {
    baseURL: `${protocol}://127.0.0.1:${port}`,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    serviceWorkers: "block",
  },
  webServer: {
    command: `${JSON.stringify(python)} ${JSON.stringify(path.join(import.meta.dirname, cspProxy ? "run_csp_proxy.py" : "run_streamlit.py"))}`,
    url: `${protocol}://127.0.0.1:${port}/_stcore/health`,
    ignoreHTTPSErrors: cspProxy,
    cwd: root,
    env: {
      ...process.env,
      SGC_CONTRIB_SET: process.env.SGC_CONTRIB_SET ?? "stock",
      PYTHONNOUSERSITE: "1",
      ...(tls
        ? {
            SGC_CSP_CERTIFICATE: tls.certificate,
            SGC_CSP_PRIVATE_KEY: tls.privateKey,
          }
        : {}),
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
      launchOptions: {
        args: [
          "--disable-features=LocalNetworkAccessChecks",
          ...(tls
            ? [`--ignore-certificate-errors-spki-list=${tls.spkiFingerprint}`]
            : []),
        ],
        ...(process.env.SGC_BROWSER_CHANNEL
          ? { channel: process.env.SGC_BROWSER_CHANNEL }
          : {}),
        ...(process.env.SGC_CHROMIUM_EXECUTABLE
          ? { executablePath: process.env.SGC_CHROMIUM_EXECUTABLE }
          : {}),
      },
    },
  }],
});
