// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { acquireManagedRoot, releaseManagedRoot } from "./managed-root";

describe("managed React roots", () => {
  it("reuses one root per host across remounts", () => {
    const host = document.createElement("div");
    const first = acquireManagedRoot(host);
    const second = acquireManagedRoot(host);
    expect(second.entry).toBe(first.entry);
    expect(second.generation).toBe(first.generation + 1);
    expect(releaseManagedRoot(host, second.entry, second.generation)).toBe(true);
  });

  it("ignores a stale cleanup from an earlier generation", () => {
    const host = document.createElement("div");
    const stale = acquireManagedRoot(host);
    const current = acquireManagedRoot(host);
    const unmount = vi.spyOn(current.entry.root, "unmount");
    // Streamlit can run the previous mount's cleanup after a remount began.
    expect(releaseManagedRoot(host, stale.entry, stale.generation)).toBe(false);
    expect(unmount).not.toHaveBeenCalled();
    expect(host.dataset.sgcStatus).toBeUndefined();
    expect(releaseManagedRoot(host, current.entry, current.generation)).toBe(true);
    expect(unmount).toHaveBeenCalledTimes(1);
    expect(host.dataset.sgcStatus).toBe("unmounted");
  });

  it("creates a fresh root after release and rejects a double release", () => {
    const host = document.createElement("div");
    const first = acquireManagedRoot(host);
    expect(releaseManagedRoot(host, first.entry, first.generation)).toBe(true);
    expect(releaseManagedRoot(host, first.entry, first.generation)).toBe(false);
    const next = acquireManagedRoot(host);
    expect(next.entry).not.toBe(first.entry);
    expect(next.generation).toBe(1);
    releaseManagedRoot(host, next.entry, next.generation);
  });

  it("keeps hosts independent", () => {
    const left = document.createElement("div");
    const right = document.createElement("div");
    const a = acquireManagedRoot(left);
    const b = acquireManagedRoot(right);
    expect(a.entry).not.toBe(b.entry);
    expect(releaseManagedRoot(right, a.entry, a.generation)).toBe(false);
    releaseManagedRoot(left, a.entry, a.generation);
    releaseManagedRoot(right, b.entry, b.generation);
  });
});
