# Clean-wheel Chromium conformance testing

The conformance gate tests the same artifact boundary users receive. CI builds
the frontend, builds core and contrib wheels once, validates their contents,
and uploads those immutable wheels. Each matrix job creates a fresh virtual
environment and installs only the core wheel plus the packages selected by
[`ci/contrib-sets.toml`](../ci/contrib-sets.toml). `uv pip check` and a package
inventory are recorded before the browser starts.

The initial matrix contains:

| Set | Installed project packages | Purpose |
| --- | --- | --- |
| `core-only` | core | Detect accidental contrib coupling |
| `stock` | core and stock contrib | Exercise PRIMS, JavaScript, raster delivery, static sprites, packed atlas crops, tenant limits, and CSP |
| `transports` | core, stock contrib, and JavaScript-only fixture | Prove a wheel can provide browser code without a Python renderer implementation |
| `hostile` | core, stock contrib, and deliberately malformed/cross-import fixtures | Prove unrequested failures and module-ownership violations are isolated |
| `javascript-stale` | core and an installed stale-identity JavaScript renderer | Prove immutable identity mismatch prevents readiness and renderer execution |
| `javascript-conflict` | core and two installed packages claiming one JavaScript kind | Prove conflicts fail before rendering in either package order |
| `javascript-adversarial` | core and a trusted-code contract-abuse fixture | Detect listener leaks and out-of-scope mutation; isolate factory, render, and cleanup failures |
| `multi-canvas` | core and stock contrib rendered in two component instances | Prove one canvas cannot revoke another canvas's atlas-page Blob URLs |

Every renderer distribution in `packages/` must occur in a set. Sets should be
chosen to cover meaningful renderer combinations without creating an
unbounded all-subsets matrix.

The projects immediately below `tests/e2e/fixtures/` intentionally remain
outside the uv workspace. CI discovers them from their project metadata, builds
them as independent wheels, and installs selected combinations so conformance
exercises the same third-party packaging boundary users encounter. Adding an
immediate-child fixture automatically enrolls it in version-range
synchronization and the full `wheels`-job fixture build, but its author must
also assign it to at least one set in `ci/contrib-sets.toml`. Release and
compatibility workflows deliberately continue to build only the positive-path
fixture required by their narrower scenario.

The required compatibility jobs also build fresh minimum and latest-supported
Python/frontend stacks, package those generated browser bundles, and run the
`transports` set in Chromium. Scheduled advisory jobs probe Python-next,
dependency prereleases, React/React Flow next, ELK next, Component v2 next,
Node-next, and Chrome Beta. See
[`dependency-lifecycle.md`](dependency-lifecycle.md) for the support and
promotion policy.

## Browser failure policy

Playwright runs pinned Chromium on a standard Ubuntu GitHub-hosted runner with
one worker in CI. The suite fails on:

- uncaught page errors or error-level console messages;
- failed requests or HTTP responses with status 400 or greater;
- any browser request to a non-local host;
- missing component readiness markers or expected renderer output;
- selection/rerun and topology-update regressions;
- serious or critical automated accessibility violations;
- CSP violations, missing JavaScript registration, external code fetches,
  missing/revoked atlas Blob pages, invalid page dimensions/digests, or
  out-of-page sprite rectangles;
- stale/conflicting installed JavaScript identities, trusted-renderer listener
  leaks or out-of-scope DOM mutation, and non-isolated renderer exceptions;
- cross-canvas atlas Blob revocation and unsupported-Pillow raster/static-image
  output;
- incorrect non-zero sprite crops, neighboring-sprite bleed, alpha loss,
  light/dark variant selection, dark-to-light fallback, or theme-triggered
  relayout;
- malformed unrequested contrib or cross-distribution import isolation failures;
- empty or implausibly sized canvas screenshots;
- fatal traceback, app-execution, or component-error signatures in the
  Streamlit server log;
- flaky tests, after retaining a trace from the retry.

Static-sprite browser coverage must use at least two transparent PNGs packed
into the same page and prove that two nodes crop different rectangles from the
same Blob URL. It also covers `contain`, `cover`, and `fill`; identical-content
deduplication; the 1x, 1.5x, and 2x resolution buckets; atomic theme swaps; and
the absence of filesystem paths, source bytes, remote requests, or CSP
violations in the browser envelope. PRIMS-derived raster tiles and static
sprites must coexist in the shared page delivery path.

HTML reports, JUnit results, traces, failure screenshots, videos, the explicit
canvas screenshot, and the complete Streamlit log are retained as workflow
artifacts. Service workers are blocked to reduce nondeterminism and to ensure a
stale cache cannot hide missing wheel assets.

## Local execution

Build wheels and prepare a selected environment:

```bash
mkdir -p wheelhouse
uv build --package streamlit-graph-canvas --out-dir wheelhouse
uv build --package streamlit-graph-canvas-contrib --out-dir wheelhouse
uv run python -m ci.verify_wheels wheelhouse
uv run python -m ci.build_conformance_environment \
  --set stock --wheelhouse wheelhouse --venv .conformance-venv
```

Exercise declared direct dependency bounds without changing project metadata:

```bash
uv run python ci/run_compatibility.py python \
  --lane minimum --python 3.12 --venv .compat-min \
  --output compatibility-minimum.json
uv run python ci/run_compatibility.py frontend \
  --lane latest --output compatibility-frontend-latest.json \
  --output-tree /tmp/sgc-core-latest
```

The frontend command builds in a temporary workspace and never changes the
committed output directory. `--output-tree` optionally materializes a complete
core package containing that selected dependency build for wheel and Chromium
conformance testing.

Then install and run Playwright:

```bash
cd tests/e2e
npm ci
npx playwright install --with-deps chromium
SGC_CONTRIB_SET=stock \
SGC_CONFORMANCE_PYTHON=../../.conformance-venv/bin/python \
npm test
```

The `--with-deps` operation needs package-manager privileges on Linux. It works
on GitHub-hosted Ubuntu runners; a restricted local environment may be able to
download Chromium but still lack its shared libraries.
