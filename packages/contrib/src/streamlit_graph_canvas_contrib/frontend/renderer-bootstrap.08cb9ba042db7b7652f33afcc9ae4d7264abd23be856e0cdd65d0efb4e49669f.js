const registrySymbol = Symbol.for("streamlit-graph-canvas.renderers.v1");
const registrationEvent = "sgc-renderer-registered-v1";
const namespace = "http://www.w3.org/2000/svg";
const buildIdentity = "dcd4641d0bb6fbfcb3f234261ccfcf388f6cd68e456e20380e7a6cdba7936b49";

function countChip({ target, data, options, palette, region }) {
  if (!Number.isSafeInteger(data)) {
    throw new Error("count-chip data must be a safe integer");
  }
  const prefix = options.prefix === undefined ? "" : String(options.prefix);
  const rect = document.createElementNS(namespace, "rect");
  rect.dataset.sgcJsChip = "true";
  rect.setAttribute("x", "0");
  rect.setAttribute("y", "0");
  rect.setAttribute("width", String(region.width));
  rect.setAttribute("height", String(region.height));
  rect.setAttribute("rx", String(Math.min(region.width, region.height) / 2));
  rect.setAttribute("fill", palette.accent);
  const text = document.createElementNS(namespace, "text");
  text.setAttribute("x", String(region.width / 2));
  text.setAttribute("y", String(region.height / 2 + 4));
  text.setAttribute("text-anchor", "middle");
  text.setAttribute("font-size", "11");
  text.setAttribute("fill", palette.on_accent);
  text.textContent = `${prefix}${data}`;
  target.append(rect, text);
}

const registrations = new Map([
  ["streamlit-graph-canvas/contrib/count-chip", {
    kind: "streamlit-graph-canvas/contrib/count-chip",
    rendererApi: 1,
    version: "0.1.0.dev0",
    buildIdentity,
    render: countChip,
  }],
]);

export default function registerRendererBootstrap({ data }) {
  const registry = globalThis[registrySymbol] ??= new Map();
  for (const expected of data.registrations) {
    const registration = registrations.get(expected.kind);
    if (!registration) {
      throw new Error(`SGC_JAVASCRIPT_FACTORY_MISSING: ${expected.kind}`);
    }
    if (registration.rendererApi !== expected.rendererApi
      || registration.version !== expected.version
      || registration.buildIdentity !== expected.buildIdentity) {
      throw new Error(`SGC_JAVASCRIPT_IDENTITY_MISMATCH: ${expected.kind}`);
    }
    const existing = registry.get(expected.kind);
    if (existing) {
      const same = existing.rendererApi === registration.rendererApi
        && existing.version === registration.version
        && existing.buildIdentity === registration.buildIdentity;
      if (!same) {
        throw new Error(`SGC_JAVASCRIPT_REGISTRATION_CONFLICT: ${expected.kind}`);
      }
      continue;
    }
    registry.set(expected.kind, registration);
    globalThis.dispatchEvent(new CustomEvent(registrationEvent, {
      detail: { kind: expected.kind },
    }));
  }
}
