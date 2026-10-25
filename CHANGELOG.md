# Changelog

All notable changes are recorded here. The format follows Keep a Changelog and
the project uses semantic versioning.

## [Unreleased]

### Maintenance

- Run full CI on pull requests and pushes to main, avoiding duplicate runs
  for feature-branch pushes while retaining manual runs.
- Refresh pinned GitHub Actions and the corresponding reviewed artifact-download
  and App-token allowlists without changing publisher permissions or commands.

### Changed

- Update the locked React/React DOM stack to 19.3.1, React type declarations
  to 19.3.0, and React Flow to 12.12.0. Promote the tested runtime upper
  endpoints while retaining the existing installation ranges and minimums.

### Fixed

- Keep advisory candidate probes running when an approved security update is
  younger than the cooldown, and record package decisions and full probe outcomes
  without promoting support endpoints.

### Security

- Require Streamlit 1.66.1 or newer, the first release compatible with Pillow 13.
- Require Pillow 13.0.0 or newer within the 13.x series for atlas and static
  sprite processing. Advance the rasterizer cache revision to isolate output
  from the previous Pillow support range.

## [0.1.0rc2] - 2026-09-11

### Added

- Clean-wheel Chromium conformance sets for core, stock contrib, and hostile
  renderer fixtures.
- Validated persistent canvas state and click-action protocol v1.
- Artifact-derived frontend licensing inventory and wheel verification.

### Changed

- Node/edge styles, named ports, theme tones, and fit-view modes are honored by
  the beta frontend.
- Renderer enablement validates only requested distributions and constrains
  Python imports to the owning distribution.

### Fixed

- Preserve measured node dimensions across controlled rerenders so named-port
  connectors do not disappear while waiting for another resize notification.
- NetworkX fallback attributes are no longer removed by eager default
  evaluation.
- CSS production assets are content-addressed.

### Canvas interaction and performance

- Add tree, collection, and per-category cutoff display policies to child groups.
- Separate edge emphasis and optional styling from relationship identity.
- Render ELK orthogonal routes inside collections; retain a smooth-step fallback
  for boundary and explicit-port connections.
- Preserve descendant disclosure state without leaking hidden groups; keep shared
  children outside competing expanded containers.
- Keep node outlines readable at low zoom with zoom-compensated SVG strokes.

- Added opt-in local name and scalar-metadata search with active-node scoping,
  numeric/text/choice filters, match navigation, and live highlighting/dimming.
- Added threshold-controlled, explicit Apply search ordering for collections and
  peer groups. Draft edits preserve positions; Clear restores normal ordering.
- Added explicit, opt-in search submissions and documented their Streamlit rerun
  cost in the API, README, and submission UI.
- Make collection reachability independent of edge order with adjacency traversal
  and indexed group lookup; add a deterministic large-chain regression check.
- Separate layout identity from schema appearance, preserving action identity
  while refreshing label policies, colors, and collection titles without ELK.
- Reuse search evaluation during geometry-only transitions and skip disabled
  search work; extract the search hook and format the touched frontend modules.
- Run budget, search, and label browser suites against candidate wheels in CI
  and the release gate. Report graph size in nodes rather than seconds.
- Avoid redundant label measurement updates and dismiss reveals on canvas movement.
- Clarify that atlas cache ceilings apply per distinct policy, with no aggregate
  process-wide ceiling across policies.

- Add budget-aware sibling context with configurable opacity, stable hierarchy
  transitions, and fixed-box label policies with global and per-type defaults.
  Shortened names reveal on delayed hover by default; controls remain available.
- Add opt-in server/browser telemetry and atlas warming for declared value domains.

### Migration notes

- Remove `AtlasScope`, `atlas_tenant`, and `AtlasPolicy.scope`,
  `max_tenant_pages`, and `max_tenant_bytes`. Equal atlas policies share a
  process-global cache. `max_pages` and `max_bytes` now bound each distinct policy
  cache, rather than each session; different policies retain separate allowances.
  Page IDs become deterministic content hashes. See
  [the atlas migration notes](docs/beta-contract.md#breaking-change-during-01-atlas-cache-scope).
- `graph_canvas(max_elements=...)` now limits rendered elements after grouping.
  Use `max_loaded_elements` to limit the supplied graph independently. Direct
  `serialize_graph` and `validate_graph` calls retain their input-budget semantics.
