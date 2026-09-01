import {
  RENDERER_REGISTRATION_EVENT,
  RENDERER_REGISTRY_SYMBOL as RENDERER_REGISTRY_SYMBOL_KEY,
} from "./contract";

export { RENDERER_REGISTRATION_EVENT } from "./contract";
export const RENDERER_REGISTRY_SYMBOL = Symbol.for(RENDERER_REGISTRY_SYMBOL_KEY);

export type JavascriptRendererContext = {
  target: SVGSVGElement;
  data: unknown;
  options: Record<string, unknown>;
  palette: Record<string, string>;
  region: { x: number; y: number; width: number; height: number };
};

export type JavascriptRendererFactory = (
  context: JavascriptRendererContext,
) => void | (() => void);

export type JavascriptRendererRegistration = {
  kind: string;
  rendererApi: number;
  version: string;
  buildIdentity: string;
  render: JavascriptRendererFactory;
};

export type JavascriptRendererRequirement = Omit<
  JavascriptRendererRegistration,
  "render"
> & { component: string; entry: string; assetHash: string };

type RegistryGlobal = typeof globalThis & {
  [RENDERER_REGISTRY_SYMBOL]?: Map<string, JavascriptRendererRegistration>;
};

export function rendererRegistry(): Map<string, JavascriptRendererRegistration> {
  const root = globalThis as RegistryGlobal;
  root[RENDERER_REGISTRY_SYMBOL] ??= new Map();
  return root[RENDERER_REGISTRY_SYMBOL];
}

export function requireJavascriptRenderer(
  requirement: JavascriptRendererRequirement,
): JavascriptRendererRegistration | null {
  const registration = rendererRegistry().get(requirement.kind);
  if (!registration) return null;
  if (
    registration.rendererApi !== requirement.rendererApi
    || registration.version !== requirement.version
    || registration.buildIdentity !== requirement.buildIdentity
  ) {
    throw new Error(
      `SGC_JAVASCRIPT_REGISTRATION_CONFLICT: ${requirement.kind}`,
    );
  }
  return registration;
}

export function cleanupJavascriptRenderer(
  cleanup: (() => void) | void,
  target: SVGSVGElement,
): void {
  try {
    cleanup?.();
  } catch (error) {
    console.error(
      "SGC_JAVASCRIPT_CLEANUP_ERROR",
      error instanceof Error ? error.message : String(error),
    );
  } finally {
    target.replaceChildren();
  }
}
