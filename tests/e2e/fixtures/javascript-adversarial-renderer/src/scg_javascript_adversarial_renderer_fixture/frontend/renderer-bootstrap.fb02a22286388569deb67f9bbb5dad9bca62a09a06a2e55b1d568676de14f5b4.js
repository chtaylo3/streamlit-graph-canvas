const symbol = Symbol.for("streamlit-graph-canvas.renderers.v1");
const eventName = "sgc-renderer-registered-v1";
const namespace = "http://www.w3.org/2000/svg";
const buildIdentity = "670d6a76183562de264d01c88a8e7838fb291b9946bff97b89f0383c0c228399";

function render({ target, data, region }) {
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
  marker.setAttribute("cx", String(region.width / 2));
  marker.setAttribute("cy", String(region.height / 2));
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
