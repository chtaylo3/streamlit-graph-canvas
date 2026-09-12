# Prepare dependency pull requests

Dependabot opens dependency PRs against main. The preparation workflow adds
mechanical companion changes to that same PR, and normal CI tests the resulting
commit. Maintainers review and merge the complete PR. Automatic publication starts
disabled; a successful candidate test never changes support policy.

## Supported versions and tested candidates

The [dependency policy](../ci/dependency-policy.toml) records `minimum` and
`latest_supported` as explicit approved endpoints. The existing `supported` field
is the package installation range, which can be wider than the tested support
interval. These are separate concepts: a version beyond `latest_supported` is
not automatically rejected or promoted.

| Lane | Versions | Effect on supported CI |
| --- | --- | --- |
| Minimum | Exact approved direct minimums | Blocking |
| Latest supported | Exact approved direct upper endpoints | Blocking |
| Locked | Versions in the committed lockfiles | Blocking |
| Latest tested | Stable candidates released at least seven days ago | Advisory |

Runtime dependency latest-supported endpoints come from the dependency set approved in
PR #27. Future promotion requires a reviewed policy change. Raising the minimum
is a separate decision because it drops older versions from the support interval.
Updating the lockfile does not itself promote either endpoint.

The candidate workflow runs weekly, on relevant PRs, and manually. It evaluates
Python, frontend, and installed-wheel Chromium stacks. Reports record selected
versions, resolved inventories where installation succeeds, timestamps, and the
actual outcome. Failures remain visible in the step summary and artifacts without
failing the supported build. A candidate that cannot install or build has failed
that stage; it has not passed browser validation. Existing prerelease and browser
beta probes remain separate advisory workflows.

`latest_supported` pins direct dependencies, not every transitive dependency.
Only the locked lane guarantees the full committed resolution. Candidate release
age selection applies to direct dependencies; package-manager resolution can
still introduce newer transitive dependencies.

## Internal JavaScript tools

Frontend build tools, formatters, type declarations, and browser-test tools take
version declarations from `package.json` and exact resolutions from
`package-lock.json`. Policy records their classification, risk, and coupling,
without duplicating version pins or defining separate support endpoints.

For example, a Prettier update from `3.6.2` to `3.9.6` can keep its new manifest
and lockfile declarations without a policy edit. Preparation checks formatting,
runs frontend tests, and rebuilds and verifies generated assets and licenses.
A formatting or build failure still blocks preparation and requires review;
the workflow does not silently reformat source files.

Minimum and latest-supported frontend lanes vary runtime dependencies while
using the current locked direct tool versions. Advisory frontend probes also
try newer eligible tools. Browser-test tools use the browser-test lockfile.
Runtime support endpoints never change as a side effect of a tool update.

Automatic preparation accepts stable exact, caret, or tilde npm declarations
and canonical public npm registry tarballs with integrity metadata. It checks
direct and transitive lockfile entries. Package aliases, Git or arbitrary URL
sources, local links, registry changes, and prerelease declarations require
manual review. Stable tool downgrades remain eligible for testing and PR review;
eligibility does not mean approval. These source checks also run independently
in the publisher, including when the artifact contains no manifest changes.

## Cooldown and automatic preparation

All four Dependabot entries have `cooldown.default-days: 7`, retaining weekly
schedules and dependency groups. The cooldown measures release age rather than
PR age. Weekly checks can add up to another scheduling interval after eligibility.
Security updates bypass Dependabot's cooldown. Candidate surveillance still uses
its seven-day filter; security PRs receive normal locked CI immediately.

The preparation command handles existing npm runtime dependency updates that fit
the approved installation ranges and existing internal JavaScript tool updates.
It restores unnecessary runtime manifest-minimum increases,
preserves resolved lock entries, rebuilds affected frontend assets and licenses,
and verifies a second generation matches. Python lock-only changes need no
generated commit. Preparation cannot alter support endpoints.

New dependencies, runtime versions outside the installation range, source edits,
and workflow or release-allowlist changes require review.
The workflow reports failure instead of guessing a policy change. Apply an
intentional policy change in a maintainer PR, then refresh the dependency branch.
Ordinary Actions updates with no companion changes still use the normal CI path.

## Configure the GitHub App

Create a private GitHub App and install it only on this repository. Disable
webhooks, OAuth user authorization, and device flow. Actions supplies the triggers;
the App supplies the authenticated identity for committing prepared files.

| Repository permission | Access |
| --- | --- |
| Contents | Read and write |
| Pull requests | Read-only |
| Actions | Read-only |
| Metadata | Read-only, required by GitHub |

Leave other permissions disabled and grant no ruleset bypass. Set these entries
under repository **Settings > Secrets and variables > Actions**:

| Kind | Name | Value |
| --- | --- | --- |
| Variable | `DEPENDENCY_PREPARATION_APP_ID` | App ID |
| Variable | `DEPENDENCY_PREPARATION_BOT` | Exact bot login, including `[bot]` |
| Variable | `DEPENDENCY_PREPARATION_WRITE` | `false` during the pilot |
| Secret | `DEPENDENCY_PREPARATION_PRIVATE_KEY` | Complete PEM private key |

Do not add the private key to Dependabot secrets. The build workflow must not have
access to it. The publisher mints an installation token scoped to this repository
only after read-only validation succeeds. It commits through GitHub's API without
using a maintainer signing key. Verify the resulting App commit is accepted by
repository signature rules during the pilot; do not weaken the rules.

## Review the publication boundary

`dependency-prepare.yml` builds on an unprivileged disposable runner. It uses
preparation scripts from the PR base, checks the exact candidate head, and emits
one JSON artifact. It has no write token or App secret and uses no shared cache.

`dependency-publish.yml` runs trusted default-branch code. It checks the workflow
ID, run attempt, source repository, PR author, signed commit authors, changed
paths, and current head/base. It reads a bounded ZIP in memory without extracting
files or executing artifact content. It rejects unexpected files, links,
duplicates, invalid hashes, and changes to scripts or resolved dependencies in
manifest outputs. Generated JavaScript remains untrusted until reviewed and
verified by ordinary CI; a path allowlist does not establish its correctness.

Bot authorship alone does not establish commit provenance. For every source
commit, the publisher additionally requires GitHub's GraphQL signature metadata
to report a valid signature made with GitHub's signing key, with an expected
signer and the same allowed bot author and commit SHA returned by REST. This
accepts GitHub's `web-flow` signing of Dependabot commits but rejects a human's
valid signature claiming bot authorship. Missing or incomplete provenance fails
closed. The configured App's API-generated commit metadata must pass the same
check during the live pilot; do not relax it to accommodate a human signing key.

The publisher uses an atomic expected-head API commit. A moved head rejects the
write. A changed base found during validation requires regeneration; branch
protection and normal CI still govern merging if main changes afterward.
Preparation is idempotent: a follow-up run on the generated commit produces no
new commit. No workflow merges, approves, or publishes a release.

The security scanner has one narrowly scoped exception for the intentional
`workflow_run` trigger. The repository's workflow-security tests enforce the
trusted checkout, permitted commands, App scope, and opt-in write boundary.

## Pilot and operate the workflow

1. Merge the implementation so the trusted publisher exists on main.
2. Keep `DEPENDENCY_PREPARATION_WRITE=false`. Refresh a representative Dependabot
   PR and inspect the preparation and publisher summaries and payload.
3. Exercise the rejection cases in the tests, then enable writes with the variable
   set to `true` after the App installation is configured.
4. Verify a prepared commit has the expected App identity, triggers normal CI,
   preserves support endpoints, and produces no further commit on the next run.
5. Verify a later Dependabot refresh/rebase still works. If generated commits
   prevent automatic rebasing, refresh or recreate the bot PR using Dependabot's
   supported controls after reviewing the branch. Do not force-push through the
   publisher or silently discard maintainer commits.

Disable writes by setting the variable to `false`; preparation reports and normal
CI continue. On stale-head or stale-attempt rejection, use the newest preparation
run or refresh the PR. Publisher errors are recorded in Actions; it does not need
PR-write permission to post comments. A PR with unexpected human commits is
handled manually rather than automatically overwritten.

## References

- [Dependabot cooldown](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#cooldown)
- [Dependabot maintainer guidance on follow-up commits](https://github.com/dependabot/dependabot-core/issues/5962#issuecomment-1298026716)
- [GitHub Security Lab: Preventing pwn requests](https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/)
- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub App registration](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)
- [GitHub signature metadata](https://docs.github.com/en/graphql/reference/git)
