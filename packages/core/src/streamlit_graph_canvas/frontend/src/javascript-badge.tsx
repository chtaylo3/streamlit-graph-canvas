import { useEffect, useRef, useState } from "react";
import {
  cleanupJavascriptRenderer,
  type JavascriptRendererRegistration,
} from "./javascript-registry";
import { tone, type Palette } from "./palette";

export type JavascriptBadgeView = {
  name: string;
  region: { x: number; y: number; width: number; height: number };
  data?: unknown;
  options?: Record<string, unknown>;
};

/**
 * Mount an installed JavaScript badge renderer into an isolated SVG target.
 *
 * A renderer that throws leaves an empty target flagged with
 * data-sgc-render-error instead of breaking the surrounding canvas.
 */
export function JavascriptBadge({
  badge,
  palette,
  registration,
}: {
  badge: JavascriptBadgeView;
  palette: Palette;
  registration: JavascriptRendererRegistration;
}) {
  const target = useRef<SVGSVGElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!target.current) return;
    const element = target.current;
    element.replaceChildren();
    try {
      const cleanup = registration.render({
        target: element,
        data: badge.data,
        options: badge.options ?? {},
        palette: Object.fromEntries(
          Object.keys(palette).map((name) => [name, tone(palette, name)]),
        ),
        region: badge.region,
      });
      setError(false);
      return () => {
        cleanupJavascriptRenderer(cleanup, element);
      };
    } catch {
      element.replaceChildren();
      setError(true);
      return undefined;
    }
  }, [badge, palette, registration]);
  return (
    <svg
      ref={target}
      className="sgc-badge"
      data-sgc-badge={badge.name}
      data-sgc-transport="javascript"
      data-sgc-render-error={error ? "true" : undefined}
      aria-hidden="true"
      style={{
        left: badge.region.x,
        top: badge.region.y,
        width: badge.region.width,
        height: badge.region.height,
      }}
      viewBox={`0 0 ${badge.region.width} ${badge.region.height}`}
    />
  );
}
