# Cross-language protocol authority

`protocol.json` is the single language-neutral authority for values that must
agree across the Python server and TypeScript browser component. Keeping this
small contract in strict JSON makes generation deterministic and prevents
either language implementation from becoming the accidental source of truth.
Human rationale stays in this document so executable consumers never need to
strip comments or accept a more permissive configuration format.

The generator writes:

- `packages/core/src/streamlit_graph_canvas/contract.py` for Python; and
- `packages/core/src/streamlit_graph_canvas/frontend/src/contract.ts` for the
  browser component.

## Version and registry fields

| Field | Meaning and change requirement |
| --- | --- |
| `schemaVersion` | Version of the authority file's own closed structure. Increment it only when generators must interpret a different JSON shape, and update generator mutation tests in the same change. |
| `codecVersion` | Version of the serialized graph/component envelope. Unsupported values fail closed before graph conversion or state application. A change requires Python serialization tests, frontend codec tests, and installed-browser migration or rejection coverage. |
| `actionProtocolVersion` | Version of browser-to-Python action semantics. Change it when an action shape or acknowledgement rule is not backward compatible, with boundary tests on both sides. |
| `rendererApiVersion` | Major contract implemented by enabled renderer packages. A change requires manifest compatibility, renderer enablement, wheel, and contrib-set Chromium evidence. |
| `rendererRegistrySymbol` | Versioned global symbol used by trusted JavaScript bootstraps to find the registry. Changing it invalidates existing bootstraps and therefore requires regenerated assets plus stale/conflict browser tests. |
| `rendererRegistrationEvent` | Versioned browser event announcing registry changes. It must move with incompatible registry semantics and requires registration, cleanup, and readiness tests. |
| `limits` | Closed set of shared resource ceilings described below. A new key requires generated consumers, rationale, and boundary tests. |

## Resource limits

All ceilings fail closed. Limit tests must cover the maximum accepted value and
maximum plus one, and must show bounded work or atomic rejection where partial
state would be unsafe.

| Limit | Unit | Protected resource or abuse boundary | Failure behavior and evidence required to change it |
| --- | --- | --- | --- |
| `maxActionBatch` | Actions in one browser batch | Server parsing, acknowledgement work, and pending browser memory | Reject an oversized batch before constructing action objects. Changes require Python and frontend queue boundary tests. |
| `maxSelection` | Selected node identifiers | Browser/server state cardinality and reconciliation work | Server rejects oversized input and the browser will not grow beyond the ceiling. Changes require limit and limit-plus-one selection tests on both sides. |
| `maxIdentifierChars` | Unicode code points in an identifier/type/operation string | Comparison, logging, serialization, and application-facing string work | Reject empty or oversized protocol identifiers with a stable diagnostic. Changes require every affected identifier field to have boundary coverage. |
| `maxBrowserStateBytes` | UTF-8 bytes of compact JSON browser state | Component state transport, serialization, and server materialization | Reject before semantic action/state processing once conservative or exact accounting exceeds the ceiling. Changes require byte-boundary tests using multibyte and escaped content. |
| `maxDataDepth` | Nested JSON container levels | Stack/visitor work and deeply nested input denial of service | The iterative data visitor stops at the boundary. Changes require depth and early-stop sentinel tests. |
| `maxDataStringChars` | Unicode code points per graph-data string or key | Memory, encoding, and UI/log amplification | Reject during the bounded data walk. Changes require value and mapping-key boundary cases. |
| `maxCollectionItems` | Entries in one JSON list or object | Broad-container traversal and allocation | Reject the container before traversing excess children. Changes require list and mapping breadth tests. |
| `maxDataValues` | Aggregate scalar and container values in graph data | Total validation/serialization CPU and memory | Stop the visitor when the cumulative count exceeds the ceiling. Changes require broad/deep aggregate and no-further-traversal evidence. |
| `maxAtlasDimension` | Pixels on one encoded page axis | Browser PNG decoding, SVG image allocation, and dimension arithmetic | Reject the whole ATLAS delta before Blob creation or cache mutation. Changes require PNG IHDR and envelope dimension boundary tests. |
| `maxAtlasDecodedPixels` | Width × height decoded pixels per ATLAS page | Decoded image memory and rasterization work | Python refuses excessive tiles and the browser atomically rejects excessive PNG dimensions. Changes require matching Python/frontend pixel tests. |
| `maxAtlasPageBytes` | Decoded bytes in one encoded PNG page | Base64 decoding, Blob memory, cache admission, and artifact transfer | Reject encoded length before decode where possible and decoded length before cache commit. Changes require base64, decoded-size, and atomicity tests. |
| `maxPrimitiveCount` | Primitives returned for one badge | Renderer validation and React/SVG node creation | Reject the entire renderer result with a stable primitive-count diagnostic. Changes require PRIMS and ATLAS boundary tests. |
| `maxPrimitiveTextChars` | Unicode code points in one `TextPrim` | DOM text size, layout work, and visual/log amplification | Reject the primitive before serialization or rasterization. Changes require exact-limit and limit-plus-one text tests. |

## Change workflow

Check generated targets without writing:

```bash
uv run python -m ci.sync_contracts --check
```

After intentionally editing `protocol.json`, regenerate them with:

```bash
uv run python -m ci.sync_contracts
```

A version or limit change must include the generated Python and TypeScript
targets and relevant Python and frontend boundary tests in the same change.
Changes affecting installed renderer identity, browser state, ATLAS, or action
semantics also require the appropriate clean-wheel Chromium set. Reviewers
should require evidence that unsupported versions and over-limit inputs leave
no acknowledged action, partial graph, Blob, cache entry, or renderer output.
