# Changelog

All notable changes are recorded here. The format follows Keep a Changelog and
the project uses semantic versioning.

## [Unreleased]

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

- NetworkX fallback attributes are no longer removed by eager default
  evaluation.
- CSS production assets are content-addressed.
