const symbol = Symbol.for("streamlit-graph-canvas.renderers.v1");
const eventName = "sgc-renderer-registered-v1";
const namespace = "http://www.w3.org/2000/svg";
const buildIdentity = "e8c175993d600300fdc4788c3916ac2e2c66dbf5c3d1bd61ef4483adb53d6146";

function render({ target, data, palette, region }) {
  const circle = document.createElementNS(namespace, "circle");
  circle.dataset.sgcJavascriptOnlyFixture = "true";
  circle.setAttribute("cx", String(region.width / 2));
  circle.setAttribute("cy", String(region.height / 2));
  circle.setAttribute("r", String(Math.min(region.width, region.height) / 2));
  circle.setAttribute("fill", palette.accent);
  const title = document.createElementNS(namespace, "title");
  title.textContent = String(data);
  circle.append(title);
  target.append(circle);
}

export default function bootstrap({ data }) {
  const registry = globalThis[symbol] ??= new Map();
  const registration = {
    kind: "streamlit-graph-canvas/fixture/javascript-only",
    rendererApi: 1,
    version: "0.1.0",
    buildIdentity,
    render,
  };
  for (const expected of data.registrations) {
    if (expected.kind !== registration.kind
      || expected.rendererApi !== registration.rendererApi
      || expected.version !== registration.version
      || expected.buildIdentity !== registration.buildIdentity) {
      throw new Error(`SGC_JAVASCRIPT_IDENTITY_MISMATCH: ${expected.kind}`);
    }
    const existing = registry.get(expected.kind);
    if (existing) {
      const same = existing.rendererApi === expected.rendererApi
        && existing.version === registration.version
        && existing.buildIdentity === registration.buildIdentity;
      if (!same) throw new Error(`SGC_JAVASCRIPT_REGISTRATION_CONFLICT: ${expected.kind}`);
      continue;
    }
    registry.set(expected.kind, registration);
    globalThis.dispatchEvent(new CustomEvent(eventName, { detail: expected.kind }));
  }
}
