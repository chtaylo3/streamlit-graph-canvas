const symbol = Symbol.for("streamlit-graph-canvas.renderers.v1");
const eventName = "sgc-renderer-registered-v1";
const buildIdentity = "48be058ed2c7728d7b4612d4d2bdf3ea9a0359649ccac2dc6b72d465bb07efdf";

export default function bootstrap({ data }) {
  const registry = globalThis[symbol] ??= new Map();
  for (const expected of data.registrations) {
    registry.set(expected.kind, { ...expected, buildIdentity, render() {} });
    globalThis.dispatchEvent(new CustomEvent(eventName, { detail: expected.kind }));
  }
}
