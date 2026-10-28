import { createRoot, type Root } from "react-dom/client";

export type ManagedRoot = { root: Root; generation: number };
const managedRoots = new WeakMap<HTMLElement, ManagedRoot>();

export function acquireManagedRoot(host: HTMLElement): {
  entry: ManagedRoot;
  generation: number;
} {
  let entry = managedRoots.get(host);
  if (!entry) {
    entry = { root: createRoot(host), generation: 0 };
    managedRoots.set(host, entry);
  }
  entry.generation += 1;
  return { entry, generation: entry.generation };
}

export function releaseManagedRoot(
  host: HTMLElement,
  entry: ManagedRoot,
  generation: number,
): boolean {
  if (managedRoots.get(host) !== entry || entry.generation !== generation)
    return false;
  host.dataset.sgcStatus = "unmounted";
  entry.root.unmount();
  managedRoots.delete(host);
  return true;
}
