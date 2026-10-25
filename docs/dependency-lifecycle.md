# Dependency lifecycle and compatibility policy

`ci/dependency-policy.toml` is the machine-readable authority for supported
toolchains and direct dependency ranges. `ci/verify_dependency_policy.py`
checks it against Python and npm metadata, both lockfiles, the supported Python
matrix, contrib sets, browser projects, committed bundle and license inventories,
pinned Actions, and the release-artifact path.

The exact generated ranges and dependency couplings are published in the
[generated dependency compatibility matrix](dependency-compatibility.generated.md).

## Inventory and risk tiers

The policy covers five dependency surfaces:

1. Python runtime: Python, Streamlit, packaging, Pillow, NetworkX, and the
   core and contrib version boundary.
2. Bundled browser runtime: Component v2, React and React DOM, React Flow, ELK, and
   their resolved transitive packages (including XYFlow system and Zustand).
3. Frontend build: Node, TypeScript, Vite, its React plugin, and Vitest.
4. Test and release: uv, pytest tooling, Playwright and Chromium, Axe, GitHub
   Actions, wheel builders, and PyPI trusted publishing.
5. Redistributed artifacts: the exact JavaScript and CSS bundle, bundled-package
   inventory,
   license inventory and text, renderer assets, and release wheels.

Critical dependencies can change runtime protocol, graph interaction and layout,
raster output, image normalization and packing, or security boundaries. High-risk
dependencies affect builds or
compatibility validation. Medium- and low-risk entries remain inventoried but do not
define a user-facing minimum unless they ship or run in user environments.

## CI lanes

| Lane | Resolution | Platforms | Required |
| --- | --- | --- | --- |
| Locked | exact `uv.lock` and npm locks | Ubuntu and Windows, Python 3.12–3.14; Node 24.x | yes |
| Release artifact | exact wheel bytes later passed to `uv publish` | Ubuntu and Chromium | yes |
| Minimum | exact supported direct minimums; coherent coupled stacks | Ubuntu and Windows; Chromium transports set | yes |
| Latest supported | exact approved direct endpoints | Ubuntu and Windows on oldest and newest Python versions; Chromium transports set | yes |
| Security | `pip-audit`, `npm audit`, dependency review, CodeQL | Ubuntu | yes |
| Latest tested | aged stable candidates with approved baseline fallback; no automatic promotion | Ubuntu, frontend, and Chromium | advisory |
| Forward | prerelease Python and runtime scenarios | scheduled Ubuntu | advisory |
| Browser beta | locked app and selected contrib in Chrome Beta | scheduled Ubuntu | advisory |

Minimum resolution does not force arbitrary transitive packages to their oldest
versions. It pins each public direct minimum and tests coupled stacks together;
this avoids combinations no upstream project supports. Test-only tooling has a
locked version but is not part of the user compatibility contract. Internal
JavaScript build and test tools use manifest declarations and lockfile versions;
policy records their risk and classification without duplicate version pins.
Minimum and latest-supported frontend lanes use the locked direct tool versions.

Every compatibility run records the resolved inventory. Browser failures retain
traces, screenshots, video, Streamlit logs, and JUnit output. The Chromium
`transports` set combines core, stock contrib, JavaScript and raster transports,
static sprites, packed atlas delivery, the shared cache path, and CSP checks.
Cache sharing and eviction are separately exercised with deterministic Python
tests.

## Dependency-specific behavioral contracts

React Flow updates must preserve measured node geometry, named handles and
multi-edges, controlled selection, keyboard activation, viewport restoration,
zoom bounds, reruns and topology changes, theme styling, cleanup without duplicate
handlers, accessibility, and style containment.

React Flow v12 remains officially supported. V13 is experimental: the measurement
callback accepts both v12 change arrays and iterable v13 changesets, retaining
only dimensions for nodes in the current scene. Compatibility probes do not
promote v13 or widen the declared v12 dependency range. Test v13 with stable React
separately from the forward lane's React canary stack to distinguish their results.
The callback uses the exported `OnNodesChange` type. Initial fit, search, and toolbar fitting use
explicit percentage padding because v12 interprets numeric padding as a ratio,
while the v13 prerelease interprets it as pixels.

Keep input normalization and explicit compatibility defaults in the shared module.
The [React Flow compatibility boundary](react-flow-compatibility.md) documents its
contract and the criteria for switching to separate build-selected version adapters.
The advisory `react-flow-stable` scenario selects the experimental React Flow
target with approved stable companions and locked tools, rejecting invalid peer
trees. Its PR workflow runs the same installed-wheel/browser contracts separately
from React-canary surveillance. Actual Streamlit theme selection, CSS layers,
nested geometry, gesture defaults, interrupted updates, and teardown/remount are
covered by shared regressions; future measurement proposals remain watch items.

The license generator has one reviewed exception for the missing LICENSE in
`react-compiler-runtime@1.0.0`: it includes the MIT notice from the exact React
commit recorded by npm, after verifying that the published runtime source matches
that commit. The exception requires the exact version, public npm tarball URL,
tarball integrity, and MIT declaration, verifies the vendored notice's SHA-256,
and records its immutable upstream URL in the generated license artifacts.
Other missing licenses still fail generation; no license is downloaded during
builds. A license included in the installed package takes precedence.

ELK updates must preserve deterministic layered direction, non-overlap,
handling of parallel edges, self-loops, cycles, and disconnected graphs, finite
coordinates, and
fail-closed validation of duplicate IDs, invalid dimensions, and unknown edge
endpoints. Coordinate equality is contractual only within a tested dependency
stack; functional geometry uses tolerances.

Streamlit and Components v2 updates must preserve registration, mount, state,
and trigger
semantics, rerun restoration, cleanup, theme propagation, asset loading, and CSP.
Pillow updates must preserve contractual raster output and static PNG
normalization for fixtures evaluated under that version. Page and tile IDs
intentionally change between Pillow versions: the normalized version and
explicit normalizer or rasterizer revisions are mandatory cache-key inputs,
preventing stale cross-version reuse. Runtime rejects
versions outside `>=13.0,<14`, and the policy verifier keeps that guard, package
metadata, and revision synchronized. Minimum and latest-supported lanes exercise
the guard on Windows and Linux; the advisory forward lane probes Pillow 14.
Pillow 13 requires Streamlit 1.66.1 or later because earlier hosts constrain
Pillow to versions below 13. This migration raises both approved Streamlit
endpoints and the package minimum, raises the Pillow minimum to 13.0.0, and
advances the atlas rasterizer revision to 2. The migration probe compared
18 rectangle, circle, and text fixtures across light/dark palettes and scale
buckets 1, 1.5, and 2: decoded pixels and encoded PNG bytes matched Pillow
12.3.0 on Linux. This fixture comparison does not guarantee identical output
for every image or platform; versioned cache identities remain mandatory.

Each Python compatibility artifact records the resolved environment and either
the accepted rasterizer identity or the guard rejection diagnostic, including
when the advisory test process exits unsuccessfully.

<a id="update-and-minimum-bump-process"></a>

## Update dependencies and minimum versions

See [dependency PR preparation](dependency-automation.md) for cooldowns,
automatic generated-file commits, GitHub App configuration, and explicit
promotion from latest tested to latest supported.

Dependabot uses the `uv` ecosystem and focused npm groups. Minor and patch updates
for coupled families share a PR; majors remain separate. Runtime updates are
never auto-merged. A dependency PR must pass locked, minimum, latest-supported, security,
wheel, and Chromium checks. Regenerate the frontend bundle and license inventory
when bundled dependencies change.

Raise a minimum only when the minimum lane is unsupportable, an upstream version
is out of security support, or the project deliberately adopts a required API.
The PR must update the policy and package metadata together, refresh locks and
artifacts, add a changelog migration note, and demonstrate the new minimum on
Ubuntu and Windows plus Chromium when browser behavior is affected. Dependabot
must not widen supported ranges automatically.

Before adopting a major version, make its advisory scenario pass; then review
upstream migration notes, security notes, and licenses, add or update behavioral
regressions,
adopt it on a branch, and run every required lane. Promote it only after the
release-artifact test passes with the exact wheels. Evaluate React with React
Flow and Streamlit with Components v2 as coupled
stacks. Major updates to ELK and Pillow also require layout and raster fixture
review.
