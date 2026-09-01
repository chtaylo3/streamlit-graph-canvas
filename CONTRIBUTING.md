# Contributing

Changes should preserve the trust boundaries and beta contract documented in
`docs/beta-contract.md`. Open an issue before expanding the wire protocol,
renderer API, transport vocabulary, or supported compatibility matrix.

## Development checks

Use Python 3.12+, uv, and Node.js 24+:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy packages/core/src packages/contrib/src
uv run python -m ci.sync_versions --check
uv run python -m ci.sync_contracts --check
uv run python -m ci.sync_renderer_assets --check
uv run python -m ci.check_renderer_javascript
uv run python ci/verify_dependency_policy.py
uv run python ci/generate_dependency_docs.py --check

cd packages/core/src/streamlit_graph_canvas/frontend
npm ci
npm test
cd ../../../../../..

uv run python ci/generate_frontend_artifacts.py --check
uv build --package streamlit-graph-canvas --out-dir wheelhouse
uv build --package streamlit-graph-canvas-contrib --out-dir wheelhouse
uv run python -m ci.build_fixture_wheels --out-dir wheelhouse
uv run python -m ci.verify_wheels wheelhouse
```

Renderer changes must add the package to a conformance set. Security-sensitive
changes need negative tests at the boundary they alter. Generated frontend
bundles are committed so a source checkout can run examples without Node; use
`uv run python ci/generate_frontend_artifacts.py --write` to intentionally
replace them. The default CI check builds in a temporary directory and leaves
the checkout unchanged.

The workspace `pyproject.toml` is the release-version authority. After changing
it, run `uv run python -m ci.sync_versions --write`; CI checks that all static
PEP 621, Streamlit component, dependency, and renderer metadata is synchronized.

## Compatibility and deprecation

During `0.x`, breaking public Python, schema, renderer, or protocol changes are
limited to minor releases and require migration notes in `CHANGELOG.md`.
Deprecations remain for at least one minor release when technically feasible.
Protocol v1 remains the documented click-only contract; new gestures require a
compatible extension or a new protocol version.

Dependency support, compatibility lanes, update grouping, and the deliberate
minimum/next-major processes are documented in
`docs/dependency-lifecycle.md`. Changes to dependency declarations must update
`ci/dependency-policy.toml` in the same pull request.
