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
    expect(remounted.get(page("a").pageId)).toEqual({
      url: "blob:shared",
      bytes: 68,
      width: 1,
      height: 1,
    });
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

  it("retains validated page dimensions and byte counts in descriptors", async () => {
    const cache = new BrowserAtlasCache(() => "blob:descriptor", () => undefined);
    const value = page("a");
    await cache.apply([value], []);
    expect(cache.get(value.pageId)).toMatchObject({
      url: "blob:descriptor",
      bytes: 68,
      width: value.width,
      height: value.height,
    });
  });

  it("enforces browser limits without evicting active pages", async () => {
    const revoked: string[] = [];
    let sequence = 0;
    const cache = new BrowserAtlasCache(
      () => `blob:limit-${++sequence}`,
      (url) => revoked.push(url),
    );
    const active = page("a");
    await cache.apply([active], []);
    cache.retain(new Set([active.pageId]));
    await cache.apply(
      [page("b")],
      [],
      { maxPages: 1, maxBytes: 1024 },
      new Set([active.pageId]),
    );
    expect(cache.ids()).toEqual([active.pageId]);
    expect(revoked).toEqual([]);
    cache.release(new Set([active.pageId]));
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

  it("rejects oversized addition and removal lists before decoding", async () => {
    let digestCalls = 0;
    const cache = new BrowserAtlasCache(
      () => "blob:unexpected",
      () => undefined,
      async () => {
        digestCalls += 1;
        return PNG_SHA256;
      },
    );
    await expect(cache.apply(
      [page("a"), page("b")],
      [],
      { maxPages: 1, maxBytes: 1024 },
    )).rejects.toThrow("SGC_ATLAS_DELTA_CARDINALITY");
    await expect(cache.apply(
      [],
      [page("a").pageId, page("b").pageId],
      { maxPages: 1, maxBytes: 1024 },
    )).rejects.toThrow("SGC_ATLAS_DELTA_CARDINALITY");
    expect(digestCalls).toBe(0);
    expect(cache.ids()).toEqual([]);
  });

  it("bounds cumulative incoming decoded bytes before creating Blob URLs", async () => {
    let created = 0;
    const cache = new BrowserAtlasCache(
      () => {
        created += 1;
        return "blob:unexpected";
      },
      () => undefined,
    );
    await expect(cache.apply(
      [page("a"), page("b")],
      [],
      { maxPages: 2, maxBytes: 100 },
    )).rejects.toThrow("SGC_ATLAS_AGGREGATE_BYTES");
    expect(created).toBe(0);
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

  it("leaves the previous page and its URL alive when a replacement delta is stale", async () => {
    let finish: ((value: string) => void) | undefined;
    let digestCalls = 0;
    const digest = (bytes: Uint8Array<ArrayBuffer>) => {
      digestCalls += 1;
      if (digestCalls === 1) return Promise.resolve(PNG_SHA256);
      return new Promise<string>((resolve) => {
        finish = resolve;
      });
    };
    const revoked: string[] = [];
    let sequence = 0;
    const cache = new BrowserAtlasCache(
      () => `blob:transition-${++sequence}`,
      (url) => revoked.push(url),
      digest,
    );
    const previous = page("a");
    const replacement = page("b");
    await cache.apply([previous], []);
    cache.retain(new Set([previous.pageId]));
    let current = true;
    const applying = cache.apply(
      [replacement],
      [previous.pageId],
      undefined,
      new Set([replacement.pageId]),
      () => current,
    );
    current = false;
    finish?.(replacement.contentSha256);
    await expect(applying).resolves.toBe(false);
    expect(cache.ids()).toEqual([previous.pageId]);
    expect(cache.get(previous.pageId)?.url).toBe("blob:transition-1");
    expect(revoked).toEqual([]);
    cache.release(new Set([previous.pageId]));
  });

  it("keeps a retired theme page alive until its presentation lease is released", async () => {
    const revoked: string[] = [];
    let sequence = 0;
    const cache = new BrowserAtlasCache(
      () => `blob:theme-${++sequence}`,
      (url) => revoked.push(url),
    );
    const light = page("a");
    const dark = page("b");
    await cache.apply([light], []);
    cache.retain(new Set([light.pageId]));
    await cache.apply(
      [dark],
      [light.pageId],
      { maxPages: 1, maxBytes: 1024 },
      new Set([light.pageId, dark.pageId]),
    );
    cache.retain(new Set([dark.pageId]));
    expect(cache.get(light.pageId)?.url).toBe("blob:theme-1");
    expect(cache.get(dark.pageId)?.url).toBe("blob:theme-2");
    expect(revoked).toEqual([]);
    cache.release(new Set([light.pageId]));
    expect(cache.get(light.pageId)).toBeUndefined();
    expect(revoked).toEqual(["blob:theme-1"]);
    cache.release(new Set([dark.pageId]));
  });
});
