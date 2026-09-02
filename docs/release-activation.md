# Release security activation

The repository implements the release boundary, but the following hosted
settings must be enabled by an administrator before the first beta tag.

The version-specific build and publication procedures are documented in
[`release-process.md`](release-process.md).

1. Protect `main`; require pull requests and the complete CI and CodeQL
   workflows, prevent force-push/deletion, and restrict bypass rights.
2. Create a `pypi` GitHub environment restricted to `v*` tags. Require an
   independent reviewer and prevent self-approval when a second maintainer is
   available. A single-maintainer repository may instead require owner
   confirmation and permit self-review as an explicitly weaker manual gate.
3. Configure a PyPI trusted publisher for `.github/workflows/release.yml`, the
   `publish` job, and the `pypi` environment for both distributions. Do not add
   an API token fallback.
4. Enable private vulnerability reporting and repository secret scanning. CI
   also runs pinned Gitleaks history scanning, but hosted alerts provide the
   private remediation channel.
5. Permit scheduled workflows to create dependency issues. Only the
   no-checkout `report-forward-failure` job receives `issues: write`.

The tag workflow first proves that the immutable tag SHA is on `main` and that
CI and CodeQL succeeded for that exact SHA. Its unprivileged job safely rebuilds
sdists offline, tests the rebuilt wheels, and stages a run/SHA/tag-bound bundle
with SBOMs and SHA-256 evidence. A separate no-environment OIDC job verifies and
attests the publishable files. The final environment-protected OIDC job verifies
the same bundle and invokes only the pinned PyPI publisher. Neither privileged
job checks out source, installs dependencies, runs repository code, or has a
general shell surface beyond the fixed `sha256sum --check` command.

Stable releases additionally require an annotated tag whose cryptographic
signature GitHub reports as verified. Alpha, beta, and release-candidate tags
may be lightweight or unsigned. The sanitized tag verification result is bound
into the release evidence.

PEP 440 development versions are built only by `ci.yml` and retained as GitHub
Actions artifacts. The release-tag verifier rejects them before any PyPI
publication path. Alpha, beta, release-candidate, and stable versions remain
eligible for the tag-triggered release workflow.

After changing any release action pin or job topology, run:

```text
uv run python ci/verify_workflow_security.py
uv run pytest tests/test_workflow_security.py
```
