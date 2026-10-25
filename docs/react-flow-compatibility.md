# React Flow compatibility boundary

React Flow v12 remains supported; v13 is experimental. Each build contains one
React Flow version. The same application source and behavioral tests run against
each installed version, using stable React before the separate React-canary probe.
Passing that probe does not change support policy.

`frontend/src/react-flow-compat.ts` and its scoped stylesheet own the verified
differences. They use public APIs shared by both versions:

- Measurement notifications become app-owned dimension updates before a React
  state updater is queued. Copy the dimension values as well as the container;
  upstream mutation and React updater replay must not change the snapshot.
- Initial fit, search, and toolbar fit use explicit percentage padding. Numeric
  padding has different semantics between v12 and v13.
- Selected-edge elevation has an explicit default preserving v12 behavior.
- Controls, minimap, handles, and background use Streamlit host theme variables,
  independent of the operating system's theme or upstream CSS layer defaults.

Keep layout, search, label rendering, transitions, and server-authoritative state
shared. Do not wrap every React Flow export or introduce runtime version parsing.
Use upstream exported callback types at the integration boundary; normalized
measurement values have application-owned types. Cache pruning and state ownership
remain in `use-measured-nodes.ts` because they are application behavior.

## When separate adapters become worthwhile

Continue with one shared implementation while public APIs, explicit defaults, and
lossless normalization preserve the same behavior on both versions. A new major,
another helper, or an unmerged proposal alone does not justify separate adapters.

The current migration does not meet the second condition below: v12 arrays and
v13 changesets are iterable, both versions accept percentage padding and explicit
edge-elevation settings, and shared public CSS variables cover theme integration.
These verified differences can stay in one implementation.

Move an affected operation to build-selected v12/v13 adapters when all three
conditions hold:

1. Reproduce a concrete incompatibility with pinned dependencies and stable React,
   identify the upstream change, and capture the required behavior in a contract
   or browser regression test.
2. A straightforward shared public API cannot preserve that behavior. Conflicting
   exports, required props, or completion lifecycles can justify a split. Needing
   runtime version checks, unsafe type assertions, or coupled flags is a sign to
   reassess; a simple local shape conversion still belongs in the shared module.
3. A small typed contract can contain the difference without duplicating application
   algorithms, and review establishes that the benefit exceeds the extra build and
   maintenance cost. If it duplicates layout/search/transitions, revisit the boundary.

Record the failing example, affected versions, alternatives considered, and why
the shared implementation is inadequate. There is no arbitrary helper-count limit.
Preserve the app-facing contract and split only divergent operations. Select the
implementation once using a typed build alias/configuration, reject unsupported
installed versions at build time, and type-check against each actual dependency.

Run identical behavioral/browser contracts for both adapters. Do not weaken tests,
fork their expected application behavior, or promote v13 support during a refactor.
Verify generated bundles, license inventories, and installed-wheel behavior for
each candidate; keep committed production assets on the supported v12 build.

The validation backlog and architecture decision are tracked in
[issue #66](https://github.com/chtaylo3/streamlit-graph-canvas/issues/66).
