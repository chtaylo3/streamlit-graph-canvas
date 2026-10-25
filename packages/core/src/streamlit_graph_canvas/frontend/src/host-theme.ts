export type HostTheme = "light" | "dark";

/** A definite host scheme wins; use the OS only for normal/light-dark hosts. */
export function resolveHostTheme(
  scheme: string,
  prefersDark: boolean,
): HostTheme {
  const modes = scheme
    .split(/\s+/u)
    .filter((mode) => mode === "light" || mode === "dark");
  const light = modes.includes("light"),
    dark = modes.includes("dark");
  return light !== dark
    ? dark
      ? "dark"
      : "light"
    : prefersDark
      ? "dark"
      : "light";
}

/** Observe ancestor theme changes, including across Component v2's shadow root.
 * Canvas internals are deliberately excluded to avoid work on pan/animation frames.
 */
export function observeHostTheme(
  host: HTMLElement,
  changed: (theme: HostTheme) => void,
): () => void {
  const media = matchMedia("(prefers-color-scheme: dark)");
  let previous: HostTheme | undefined;
  let frame: number | undefined;
  const update = () => {
    frame = undefined;
    const theme = resolveHostTheme(
      getComputedStyle(host).colorScheme,
      media.matches,
    );
    if (theme !== previous) {
      previous = theme;
      host.dataset.sgcTheme = theme;
      changed(theme);
    }
  };
  const schedule = () => {
    if (frame === undefined) frame = requestAnimationFrame(update);
  };
  const observer = new MutationObserver(schedule);
  let ancestor: Element | null = host;
  while (ancestor) {
    const root: Node = ancestor.getRootNode();
    ancestor =
      ancestor.parentElement ?? (root instanceof ShadowRoot ? root.host : null);
    if (ancestor)
      observer.observe(ancestor, {
        attributes: true,
        attributeFilter: ["class", "style", "data-theme"],
      });
  }
  media.addEventListener("change", schedule);
  update();
  return () => {
    observer.disconnect();
    media.removeEventListener("change", schedule);
    if (frame !== undefined) cancelAnimationFrame(frame);
  };
}
