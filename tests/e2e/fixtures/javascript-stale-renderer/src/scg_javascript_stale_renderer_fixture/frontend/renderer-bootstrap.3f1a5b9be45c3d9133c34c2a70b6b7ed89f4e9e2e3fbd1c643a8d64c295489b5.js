const symbol = Symbol.for("streamlit-graph-canvas.renderers.v1");
const eventName = "sgc-renderer-registered-v1";
const buildIdentity = "c521c2647cd54409d7a911c6162081660d58f90996d5082fe68d637f8a08ad5b";
const staleIdentity = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";

export default function bootstrap({ data }) {
  const registry = globalThis[symbol] ??= new Map();
  for (const expected of data.registrations) {
    registry.set(expected.kind, {
      kind: expected.kind,
      rendererApi: expected.rendererApi,
      version: expected.version,
      buildIdentity: staleIdentity,
      render() {
        throw new Error("stale renderer must never execute");
      },
    });
    globalThis.dispatchEvent(new CustomEvent(eventName, { detail: expected.kind }));
  }
}

void buildIdentity;
