# Release security activation

The repository implements the release boundary, but the following hosted
settings must be enabled by an administrator before the first beta tag.

1. Protect `main`; require pull requests and the complete CI and CodeQL
   workflows, prevent force-push/deletion, and restrict bypass rights.
2. Create a `pypi` GitHub environment restricted to `v*` tags, require an
   independent reviewer, and prevent the triggering actor from self-approving.
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

After changing any release action pin or job topology, run:

```text
uv run python ci/verify_workflow_security.py
uv run pytest tests/test_workflow_security.py
```
