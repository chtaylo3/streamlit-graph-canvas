# Build and release process

The workspace version in the root `pyproject.toml` is authoritative. Release
metadata must be synchronized with `uv run python -m ci.sync_versions --write`
and committed through a pull request before creating a release tag.

The project uses three distinct paths for development builds, public
prereleases, and stable releases. Development distributions remain GitHub
Actions artifacts. Alpha, beta, release-candidate, and stable distributions are
published to PyPI by `.github/workflows/release.yml` using Trusted Publishing.

## Development wheels

Development versions use the PEP 440 `.devN` suffix, for example
`0.1.0.dev1`. They are build artifacts, not public PyPI releases.

1. Create a branch and set the root version to the next unused `.devN` value.
2. Synchronize metadata and the lock file:

   ```bash
   uv run python -m ci.sync_versions --write
   uv lock
   uv run python -m ci.sync_versions --check
   uv run python -m ci.sync_renderer_assets --check
   ```

   Version synchronization rewrites any shipped JavaScript renderer versions
   and automatically refreshes their build identities, content-addressed
   filenames, and manifest references.

3. Push the branch, or manually run the `CI` workflow for that branch:

   ```bash
   gh workflow run ci.yml --ref BRANCH
   ```

4. Download the `conformance-wheelhouse` artifact from the successful run. It
   contains verified wheels, source distributions, SBOMs, checksums, and locked
   constraints and is retained for 30 days.

Do not create release tags for development builds. As a fail-closed safeguard,
the release-tag verifier rejects every PEP 440 development release before the
release workflow builds or publishes it. The `CI` workflow has read-only
repository permissions, does not use the `pypi` environment, and is not a PyPI
Trusted Publisher.

## Alpha, beta, and release-candidate releases

Public prereleases use lowercase PEP 440 suffixes:

- alpha: `0.1.0a1`, tagged `v0.1.0a1`
- beta: `0.1.0b1`, tagged `v0.1.0b1`
- release candidate: `0.1.0rc1`, tagged `v0.1.0rc1`

For each prerelease:

1. Create a release branch from current `main` and set the root version.
2. Synchronize metadata and renderer assets, update `uv.lock`, run the
   development and release checks, and merge the signed version commit through
   a pull request:

   ```bash
   uv run python -m ci.sync_versions --write
   uv lock
   uv run python -m ci.sync_versions --check
   uv run python -m ci.sync_renderer_assets --check
   ```
3. Confirm `ci.yml` and `codeql.yml` succeeded for the exact merge SHA.
4. Create an unsigned lightweight tag and push it. Use `--no-sign`
   explicitly so a maintainer's local `tag.gpgsign` setting cannot silently
   turn the prerelease into a signed annotated tag:

   ```bash
   git tag --no-sign v0.1.0rc1
   git push origin v0.1.0rc1
   ```

5. Review the `Publish release` run and approve its `pypi` environment
   deployment. The workflow verifies the exact tag, protected-main ancestry,
   exact-SHA CI results, artifacts, conformance suite, checksums, and
   attestations before publishing both distributions.

Prerelease tag rules permit deletion but prohibit moving an existing tag. A
tag may be deleted only when publication never occurred or failed before any
file reached PyPI. Never reuse its version identifier. Once any file is
published, keep the Git tag and yank a defective PyPI release before publishing
the next prerelease number.

## Stable releases

Stable versions omit a suffix, for example `0.1.0` with tag `v0.1.0`. Follow
the same version PR, exact-SHA checks, release workflow, and environment
approval used for a public prerelease, but create a signed annotated tag:

```bash
git tag -s v0.1.0 -m "streamlit-graph-canvas v0.1.0"
git tag -v v0.1.0
git push origin v0.1.0
```

Stable tag rules prohibit updates, deletion, and force pushes. The existing
`main` ruleset also requires verified commit signatures.

The release gate requires GitHub to report the stable annotated-tag signature
as verified before it builds or publishes artifacts. It also records the tag
object SHA and sanitized verification result in the release evidence. A
lightweight, unsigned, invalid, expired, or otherwise unverified stable tag
fails closed. GitHub's tag-ruleset `Require signed commits` control verifies
commits, not annotated tag objects, so it is not a substitute for this
release-gate check.

## Hosted boundaries

The GitHub `pypi` environment accepts only `v*` tags and provides the manual
deployment boundary. PyPI Trusted Publishers authorize only
`.github/workflows/release.yml` with the `pypi` environment, independently for
`streamlit-graph-canvas` and `streamlit-graph-canvas-contrib`. Do not authorize
`ci.yml` and do not add an API-token fallback.

The environment tag pattern is intentionally only a secondary check: GitHub
environment patterns cannot express all PEP 440 distinctions reliably. The
release verifier is the semantic control that excludes `.devN` versions.
