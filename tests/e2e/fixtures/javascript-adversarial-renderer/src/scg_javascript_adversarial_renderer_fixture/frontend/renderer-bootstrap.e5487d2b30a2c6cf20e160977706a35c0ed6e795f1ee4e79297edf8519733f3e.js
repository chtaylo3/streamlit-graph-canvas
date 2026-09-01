const symbol = Symbol.for("streamlit-graph-canvas.renderers.v1");
const eventName = "sgc-renderer-registered-v1";
const namespace = "http://www.w3.org/2000/svg";
const buildIdentity = "b80a462fe72be522ca0abeea3dc1660cdd5cdcf5dc16b235f6718ea4e42ec658";

function render({ target, data }) {
  if (data === "listener-leak") {
    const listener = () => {
      globalThis.__sgcLeakedListenerCalls = (globalThis.__sgcLeakedListenerCalls ?? 0) + 1;
    };
    globalThis.addEventListener("sgc-leak-probe", listener);
  }
  if (data === "dom-mutation") {
    const escaped = document.createElement("div");
    escaped.dataset.sgcOutOfScopeMutation = "true";
    document.body.append(escaped);
  }
  if (data === "factory-throw") {
    throw new Error("SGC_JAVASCRIPT_FACTORY_THROW");
  }
  const marker = document.createElementNS(namespace, "circle");
  marker.dataset.sgcAdversarialBehavior = String(data);
  marker.setAttribute("r", "4");
  target.append(marker);
  if (data === "render-throw") {
    throw new Error("SGC_JAVASCRIPT_RENDER_THROW");
  }
  if (data === "cleanup-throw") {
    return () => {
      throw new Error("SGC_JAVASCRIPT_CLEANUP_FIXTURE");
    };
  }
  return undefined;
}

export default function bootstrap({ data }) {
  const registry = globalThis[symbol] ??= new Map();
  for (const expected of data.registrations) {
    registry.set(expected.kind, {
      kind: expected.kind,
      rendererApi: expected.rendererApi,
      version: expected.version,
      buildIdentity,
      render,
    });
    globalThis.dispatchEvent(new CustomEvent(eventName, { detail: expected.kind }));
  }
}
