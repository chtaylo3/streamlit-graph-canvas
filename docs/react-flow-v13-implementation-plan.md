# React Flow v12/v13 assessment and implementation plans

Assessment: 2026-10-25, PR #67. V12 remains supported; v13 remains experimental.
CI, CodeQL, and all supported fixture/platform checks passed at `bb9784d` before
this increment. A new PR head needs fresh evidence.

## Evidence and scope

| Area | Evidence | Decision |
| --- | --- | --- |
| Measurement notifications | Published v13 uses iterable changesets instead of v12 arrays. | Keep copied, app-owned dimension updates in the existing shared adapter. |
| Fit spacing and stacking | Numeric padding changes meaning; selected-edge elevation defaults change. | Keep explicit percentages and v12 elevation settings; test real controls and grouped/overlapping edges. |
| Theme selection | Upstream #5843 removes `colorMode`; #5844 layers library CSS. Live Streamlit inspection shows a definite inherited `color-scheme`, overridden by our root and v13. Atlas selection independently uses OS media queries. | Make palette, canvas chrome, overlays, and atlas consume the host theme. Use shared CSS inheritance/public variables, without version-specific props. |
| Edge labels and overlays | We render `BaseEdge` labels. The previous v12 wheel renders black label text in a selected dark host theme; the overlay also hardcodes white/black and portals outside the theme scope. | Map native edge-label text/background through common CSS variables; keep overlays in the themed shadow root and test real labels in both versions. |
| Parent geometry | Merged #5972 changes measured parent/child absolute-position processing. | Add nested expansion, resize, named-port, rerun, removal/reappearance regressions. Add a workaround only for a reproduced failure. |
| Controlled state/lifecycle | V13 splits internal stores. Existing coverage misses rapid transitions, user interruption, and repeated teardown/remount on both versions. | Add outcome-based regressions, retaining server ownership and per-canvas isolation. |
| Measurement completion | Async `updateNodeInternals` proposal #5979 is still unmerged; the tested prerelease returns void. | Assert eventual DOM geometry, not frame counts. No speculative completion adapter. |
| Store hooks, mouse-button arrays, experimental groups | We do not use the affected direct store hooks or `panOnDrag` arrays. Group/changeset proposals remain unsettled. | Keep watch items in #66; do not add unused APIs or version flags. |
| Repeatability | Current forward React Flow probes also upgrade React to canary. | Add an isolated stable-React v13 scenario and advisory PR browser job, separate from canary surveillance. |

Sources: [major roadmap and discussion](https://github.com/xyflow/xyflow/pull/5866),
[themes](https://github.com/xyflow/xyflow/pull/5843),
[CSS layers](https://github.com/xyflow/xyflow/pull/5844),
[geometry](https://github.com/xyflow/xyflow/pull/5972),
[measurement proposal](https://github.com/xyflow/xyflow/pull/5979),
[Streamlit theme contract](https://docs.streamlit.io/develop/concepts/custom-components/components-v2/theming).

## Plan A: complete the shared compatibility behavior

1. Reproduce host/OS disagreement through Streamlit's actual Light/Dark/System
   menu, including switching after mount. Establish a failing test before fixing it.
2. Inherit the host's computed color scheme through the canvas and React Flow
   root. Retain scoped public theme-variable mappings and application focus/overlay
   rules in a deliberate application CSS layer above the library layer.
3. Observe host theme changes across the component's shadow boundary, coalescing
   notifications and cleaning observers/listeners on teardown. Use the same resolved
   theme for atlas requests; use the OS only when the host has no definite scheme.
4. Keep dimensions, viewport defaults, and stacking in the shared module. Leave
   app state/layout algorithms outside it. No build-selected adapters are justified
   because all required operations still have shared public APIs.

## Plan B: close the regression and repeatability gaps

1. Add actual menu selection, live switching, OS disagreement, palette/atlas/sprite
   coherence, native edge labels, focus/label overlays, and competing-layer CSS checks.
2. Add a dedicated nested-group/lifecycle gallery and shared browser assertions for
   expansion/collapse, parent resize, named handles, authoritative removal/reappearance,
   presentation reruns, interrupted transitions, saved viewports, and remount isolation.
   Exercise rapid topology/presentation changes during a pending scene and default
   wheel, pinch, and double-click zoom. For grouped edges, preserve the supported
   endpoint-layer elevation above group backgrounds rather than freezing their z-index.
3. Freeze stable React and supported companion/tool versions when selecting only
   the experimental React Flow target. Reject an invalid dependency tree in that
   scenario. Run the same contracts on v12 and v13; keep canary separate.
4. Build licensed wheels, verify contents, run installed-wheel suites with no retries,
   regenerate/reproduce supported v12 assets, and update #66 and PR #67 with exact
   results and any remaining limitations. Required supported CI remains blocking;
   experimental CI remains advisory.

The transition criteria in [the compatibility design](react-flow-compatibility.md)
apply if testing reveals incompatible semantics. A proposal or test gap alone is
insufficient evidence for a version-specific adapter.

## Implementation outcome

Both plans are implemented in PR #67. The old wheel fails the new
real-menu theme contract (`light dark` instead of the selected definite scheme),
and fails the native edge-label contract (black text instead of host text color).
The fixes use shared web/CSS APIs; no version-selected adapter is required.

The nested geometry, overlapping/grouped edge layers, resize, ID removal/reappearance,
user-interrupted transition, rapid revision, and repeated teardown/remount contracts
pass on both versions. These are now regressions, not reasons to add speculative
store or geometry workarounds. The new advisory workflow retains complete reports,
checks the actual peer tree, and runs shared contracts with stable React. CodeQL and
the required supported matrices must run again on the updated PR head.
