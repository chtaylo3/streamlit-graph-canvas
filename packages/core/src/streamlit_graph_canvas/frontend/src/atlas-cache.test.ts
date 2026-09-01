import { afterEach, describe, expect, it, vi } from "vitest";
import {
  acquireBrowserAtlasCache,
  BrowserAtlasCache,
  clearSharedAtlasCachesForTests,
  releaseBrowserAtlasCache,
  type AtlasPageDelta,
} from "./atlas-cache";

const PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";
const PNG_SHA256 = "431ced6916a2a21a156e38701afe55bbd7f88969fbbfc56d7fe099d47f265460";

afterEach(() => {
  clearSharedAtlasCachesForTests();
  vi.useRealTimers();
});

function page(id: string): AtlasPageDelta {
  return {
    pageId: id.repeat(64),
    contentSha256: PNG_SHA256,
    mediaType: "image/png",
    base64: PNG_BASE64,
    width: 1,
    height: 1,
  };
}

describe("browser atlas cache", () => {
  it("preserves URLs across brief same-key remounts and clears removed canvases", async () => {
    vi.useFakeTimers();
    const revoked: string[] = [];
    const create = () => new BrowserAtlasCache(
      () => "blob:shared",
      (url) => revoked.push(url),
    );
    const first = acquireBrowserAtlasCache("canvas", create);
    await first.apply([page("a")], []);
    releaseBrowserAtlasCache("canvas");
    await vi.advanceTimersByTimeAsync(1_000);
    const remounted = acquireBrowserAtlasCache("canvas", create);
    expect(remounted).toBe(first);
    expect(remounted.get(page("a").pageId)).toBe("blob:shared");
    await vi.advanceTimersByTimeAsync(5_000);
    expect(revoked).toEqual([]);
    releaseBrowserAtlasCache("canvas");
    await vi.advanceTimersByTimeAsync(5_000);
    expect(revoked).toEqual(["blob:shared"]);
  });

  it("deduplicates validated pages and revokes removed Blob URLs", async () => {
    const revoked: string[] = [];
    let sequence = 0;
    const cache = new BrowserAtlasCache(
      () => `blob:test-${++sequence}`,
      (url) => revoked.push(url),
    );
    const value = page("a");
    await cache.apply([value], []);
    await cache.apply([value], []);
    expect(cache.ids()).toEqual([value.pageId]);
    expect(sequence).toBe(1);
    await cache.apply([], [value.pageId]);
    expect(revoked).toEqual(["blob:test-1"]);
    expect(cache.ids()).toEqual([]);
  });

  it("enforces browser limits without evicting active pages", async () => {
    const revoked: string[] = [];
    let sequence = 0;
    const cache = new BrowserAtlasCache(
      () => `blob:limit-${++sequence}`,
      (url) => revoked.push(url),
    );
    const active = page("a");
    await cache.apply(
      [page("b"), active],
      [],
      { maxPages: 1, maxBytes: 1024 },
      new Set([active.pageId]),
    );
    expect(cache.ids()).toEqual([active.pageId]);
    expect(revoked).toEqual([]);
  });

  it.each([
    ["digest", { contentSha256: "0".repeat(64) }, "SGC_ATLAS_DIGEST"],
    ["base64", { base64: "!!!!" }, "SGC_ATLAS_BASE64"],
    ["media", { mediaType: "image/jpeg" }, "SGC_ATLAS_DELTA_SHAPE"],
    ["dimensions", { width: 2 }, "SGC_ATLAS_DIMENSIONS"],
  ])("rejects invalid %s atomically", async (_name, update, diagnostic) => {
    const revoked: string[] = [];
    const cache = new BrowserAtlasCache(
      () => "blob:stable",
      (url) => revoked.push(url),
    );
    const stable = page("a");
    await cache.apply([stable], []);
    const invalid = { ...page("b"), ...update } as AtlasPageDelta;
    await expect(cache.apply([invalid], [stable.pageId])).rejects.toThrow(
      diagnostic,
    );
    expect(cache.ids()).toEqual([stable.pageId]);
    expect(revoked).toEqual([]);
  });

  it("rejects duplicate and contradictory deltas before mutation", async () => {
    const cache = new BrowserAtlasCache(() => "blob:test", () => undefined);
    const value = page("a");
    await expect(cache.apply([value, value], [])).rejects.toThrow(
      "SGC_ATLAS_DELTA_DUPLICATE",
    );
    await expect(cache.apply([value], [value.pageId])).rejects.toThrow(
      "SGC_ATLAS_DELTA_CONFLICT",
    );
    expect(cache.ids()).toEqual([]);
  });

  it("does not install a page whose async generation was cancelled", async () => {
    let finish: ((value: string) => void) | undefined;
    const digest = () => new Promise<string>((resolve) => {
      finish = resolve;
    });
    const cache = new BrowserAtlasCache(() => "blob:late", () => undefined, digest);
    const value = page("a");
    let current = true;
    const applying = cache.apply([value], [], undefined, new Set(), () => current);
    current = false;
    finish?.(value.contentSha256);
    await expect(applying).resolves.toBe(false);
    expect(cache.ids()).toEqual([]);
  });
});
