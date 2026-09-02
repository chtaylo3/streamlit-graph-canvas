# Dependency lifecycle and compatibility policy

`ci/dependency-policy.toml` is the machine-readable authority for supported
toolchains and direct dependency ranges. `ci/verify_dependency_policy.py`
checks it against Python and npm metadata, both lockfiles, the supported Python
matrix, contrib sets, browser projects, committed bundle/license inventories,
pinned Actions, and the release-artifact path.

The exact generated ranges and dependency couplings are published in
[`dependency-compatibility.generated.md`](dependency-compatibility.generated.md).

## Inventory and risk tiers

The policy covers five dependency surfaces:

1. Python/runtime: Python, Streamlit, packaging, Pillow, NetworkX, and the
   core/contrib version boundary.
2. Bundled browser runtime: Component v2, React/React DOM, React Flow, ELK, and
   their resolved transitive packages (including XYFlow system and Zustand).
3. Frontend build: Node, TypeScript, Vite, its React plugin, and Vitest.
4. Test and release: uv, pytest tooling, Playwright/Chromium, Axe, GitHub
   Actions, wheel builders, and PyPI trusted publishing.
5. Redistributed artifacts: the exact JS/CSS bundle, bundled-package inventory,
   license inventory/text, renderer assets, and release wheels.

Critical dependencies can change runtime protocol, graph interaction/layout,
raster output, image normalization/packing, or security boundaries. High-risk
dependencies affect builds or
compatibility validation. Medium/low-risk entries remain inventoried but do not
define a user-facing minimum unless they ship or run in user environments.

## CI lanes

| Lane | Resolution | Platforms | Required |
| --- | --- | --- | --- |
| Locked | exact `uv.lock` and npm locks | Ubuntu and Windows, Python 3.12–3.14; Node 24.x | yes |
| Release artifact | exact wheel bytes later passed to `uv publish` | Ubuntu + Chromium | yes |
| Minimum | exact supported direct minimums; coherent coupled stacks | Ubuntu and Windows; Chromium transports set | yes |
| Latest | fresh resolution inside declared ranges | Ubuntu and Windows on oldest/newest Python; Chromium transports set | yes |
| Security | `pip-audit`, `npm audit`, dependency review, CodeQL | Ubuntu | yes |
| Forward | prerelease/next Python and runtime scenarios | scheduled Ubuntu | advisory |
| Browser beta | locked app and selected contrib in Chrome Beta | scheduled Ubuntu | advisory |

Minimum resolution does not force arbitrary transitive packages to their oldest
versions. It pins each public direct minimum and tests coupled stacks together;
this avoids combinations no upstream project supports. Test-only tooling has a
locked version but is not part of the user compatibility contract.

Every compatibility run records the resolved inventory. Browser failures retain
traces, screenshots, video, Streamlit logs, and JUnit output. The Chromium
`transports` set combines core, stock contrib, JavaScript and raster transports,
static sprites, packed atlas delivery, the tenant-scoped cache path, and CSP
checks. Tenant isolation and eviction are separately exercised with
deterministic Python tests.

## Dependency-specific behavioral contracts

React Flow updates must preserve measured node geometry, named handles and
multi-edges, controlled selection, keyboard activation, viewport restoration,
zoom bounds, reruns/topology changes, theme styling, cleanup without duplicate
handlers, accessibility, and style containment.

ELK updates must preserve deterministic layered direction, non-overlap,
parallel/self-loop/cyclic/disconnected graph handling, finite coordinates, and
fail-closed validation of duplicate IDs, invalid dimensions, and unknown edge
endpoints. Coordinate equality is contractual only within a tested dependency
stack; functional geometry uses tolerances.

Streamlit/Component v2 updates must preserve registration, mount/state/trigger
semantics, rerun restoration, cleanup, theme propagation, asset loading, and CSP.
Pillow updates must preserve contractual raster output and static PNG
normalization for fixtures evaluated under that version. Page and tile IDs
intentionally change between Pillow versions: the normalized version and
explicit normalizer/rasterizer revisions are mandatory cache-key inputs,
preventing stale cross-version reuse. Runtime rejects
versions outside `>=12.3,<13`, and the policy verifier keeps that guard, package
metadata, and revision synchronized. Minimum and latest-supported lanes exercise
the guard on Windows and Linux; the advisory forward lane probes Pillow 13.
Each Python compatibility artifact records the resolved environment and either
the accepted rasterizer identity or the guard rejection diagnostic, including
when the advisory test process exits unsuccessfully.

## Update and minimum-bump process

Dependabot uses the `uv` ecosystem and focused npm groups. Minor/patch updates
for coupled families share a PR; majors remain separate. Runtime updates are
never auto-merged. A dependency PR must pass locked, minimum, latest, security,
wheel, and Chromium checks. Regenerate the frontend bundle and license inventory
when bundled dependencies change.

Raise a minimum only when the minimum lane is unsupportable, an upstream version
is out of security support, or the project deliberately adopts a required API.
The PR must update the policy and package metadata together, refresh locks and
artifacts, add a changelog migration note, and demonstrate the new minimum on
Ubuntu and Windows plus Chromium when browser behavior is affected. Dependabot
must not widen supported ranges automatically.

For a next major, first keep an advisory scenario green; then review upstream
migration/security notes and licenses, add or update behavioral regressions,
adopt it on a branch, and run every required lane. Promote it only after the
release-artifact test passes with the exact wheels. React/React Flow and
Streamlit/Component v2 majors are evaluated as coupled stacks; ELK and Pillow
majors additionally require layout/raster fixture review.
