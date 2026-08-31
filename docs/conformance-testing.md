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
| `stock` | core and stock contrib | Exercise public composition and PRIMS |

Every renderer distribution in `packages/` must occur in a set. Sets should be
chosen to cover meaningful renderer combinations without creating an
unbounded all-subsets matrix.

## Browser failure policy

Playwright runs pinned Chromium on a standard Ubuntu GitHub-hosted runner with
one worker in CI. The suite fails on:

- uncaught page errors or error-level console messages;
- failed requests or HTTP responses with status 400 or greater;
- any browser request to a non-local host;
- missing component readiness markers or expected renderer output;
- selection/rerun and topology-update regressions;
- empty or implausibly sized canvas screenshots;
- fatal traceback, app-execution, or component-error signatures in the
  Streamlit server log;
- flaky tests, after retaining a trace from the retry.

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
uv run python ci/verify_wheels.py wheelhouse
uv run python ci/build_conformance_environment.py \
  --set stock --wheelhouse wheelhouse --venv .conformance-venv
```

Then install and run Playwright:

```bash
cd conformance
npm ci
npx playwright install --with-deps chromium
SGC_CONTRIB_SET=stock \
SGC_CONFORMANCE_PYTHON=../.conformance-venv/bin/python \
npm test
```

The `--with-deps` operation needs package-manager privileges on Linux. It works
on GitHub-hosted Ubuntu runners; a restricted local environment may be able to
download Chromium but still lack its shared libraries.
