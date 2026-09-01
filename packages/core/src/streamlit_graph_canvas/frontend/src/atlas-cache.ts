import {
  MAX_ATLAS_DECODED_PIXELS,
  MAX_ATLAS_DIMENSION,
  MAX_ATLAS_PAGE_BYTES,
} from "./contract";

export type AtlasPageDelta = {
  pageId: string;
  contentSha256: string;
  mediaType: "image/png";
  base64: string;
  width: number;
  height: number;
};

type CachedPage = { url: string; bytes: number };
type PreparedPage = { page: AtlasPageDelta; bytes: Uint8Array<ArrayBuffer> };
type Digest = (bytes: Uint8Array<ArrayBuffer>) => Promise<string>;

const SHA256 = /^[0-9a-f]{64}$/;
const BASE64 = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const PAGE_FIELDS = [
  "base64",
  "contentSha256",
  "height",
  "mediaType",
  "pageId",
  "width",
].sort();
const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];
const CACHE_RELEASE_GRACE_MS = 5_000;

type SharedCache = {
  cache: BrowserAtlasCache;
  leases: number;
  releaseTimer?: ReturnType<typeof setTimeout>;
};
const sharedCaches = new Map<string, SharedCache>();

async function sha256(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function decodeBase64(value: string, maxBytes: number): Uint8Array<ArrayBuffer> {
  if (!value || value.length % 4 !== 0 || !BASE64.test(value)) {
    throw new Error("SGC_ATLAS_BASE64: page data is not canonical base64");
  }
  const padding = value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0;
  const estimated = value.length / 4 * 3 - padding;
  if (estimated > Math.min(maxBytes, MAX_ATLAS_PAGE_BYTES)) {
    throw new Error("SGC_ATLAS_PAGE_BYTES: encoded page exceeds its byte limit");
  }
  const binary = atob(value);
  if (binary.length !== estimated) {
    throw new Error("SGC_ATLAS_BASE64: decoded page length is inconsistent");
  }
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function validatePng(
  bytes: Uint8Array<ArrayBuffer>,
  width: number,
  height: number,
): void {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (
    bytes.length < 24
    || PNG_SIGNATURE.some((value, index) => bytes[index] !== value)
    || view.getUint32(8) !== 13
    || String.fromCharCode(...bytes.slice(12, 16)) !== "IHDR"
  ) {
    throw new Error("SGC_ATLAS_PNG: page is not a supported PNG");
  }
  const pngWidth = view.getUint32(16);
  const pngHeight = view.getUint32(20);
  if (
    !Number.isSafeInteger(width)
    || !Number.isSafeInteger(height)
    || width <= 0
    || height <= 0
    || width > MAX_ATLAS_DIMENSION
    || height > MAX_ATLAS_DIMENSION
    || width * height > MAX_ATLAS_DECODED_PIXELS
    || pngWidth !== width
    || pngHeight !== height
  ) {
    throw new Error("SGC_ATLAS_DIMENSIONS: PNG dimensions are invalid");
  }
}

async function preparePage(
  page: AtlasPageDelta,
  maxBytes: number,
  digest: Digest,
): Promise<PreparedPage> {
  if (
    page === null
    || typeof page !== "object"
    || JSON.stringify(Object.keys(page).sort()) !== JSON.stringify(PAGE_FIELDS)
    || !SHA256.test(page.pageId)
    || !SHA256.test(page.contentSha256)
    || page.mediaType !== "image/png"
  ) {
    throw new Error("SGC_ATLAS_DELTA_SHAPE: page fields are invalid");
  }
  const bytes = decodeBase64(page.base64, maxBytes);
  validatePng(bytes, page.width, page.height);
  if (await digest(bytes) !== page.contentSha256) {
    throw new Error("SGC_ATLAS_DIGEST: page content digest does not match");
  }
  return { page, bytes };
}

export class BrowserAtlasCache {
  private readonly pages = new Map<string, CachedPage>();

  constructor(
    private readonly createUrl = (blob: Blob) => URL.createObjectURL(blob),
    private readonly revokeUrl = (url: string) => URL.revokeObjectURL(url),
    private readonly digest: Digest = sha256,
  ) {}

  async apply(
    pages: readonly AtlasPageDelta[],
    removedPageIds: readonly string[],
    limits?: { maxPages: number; maxBytes: number },
    protectedPageIds: ReadonlySet<string> = new Set(),
    isCurrent: () => boolean = () => true,
  ): Promise<boolean> {
    const additions = new Set<string>();
    for (const page of pages) {
      if (additions.has(page.pageId)) {
        throw new Error("SGC_ATLAS_DELTA_DUPLICATE: duplicate page addition");
      }
      additions.add(page.pageId);
    }
    const removals = new Set<string>();
    for (const pageId of removedPageIds) {
      if (!SHA256.test(pageId) || removals.has(pageId) || additions.has(pageId)) {
        throw new Error("SGC_ATLAS_DELTA_CONFLICT: invalid page removal");
      }
      removals.add(pageId);
    }
    const maxBytes = limits?.maxBytes ?? MAX_ATLAS_PAGE_BYTES;
    const prepared: PreparedPage[] = [];
    for (const page of pages) {
      prepared.push(await preparePage(page, maxBytes, this.digest));
      if (!isCurrent()) return false;
    }

    const prospective = new Map(this.pages);
    for (const pageId of removals) prospective.delete(pageId);
    for (const item of prepared) {
      prospective.set(item.page.pageId, { url: "", bytes: item.bytes.byteLength });
    }
    const evictions = new Set<string>();
    if (limits) {
      const prospectiveBytes = () => [...prospective.values()]
        .reduce((total, page) => total + page.bytes, 0);
      while (
        prospective.size > limits.maxPages
        || prospectiveBytes() > limits.maxBytes
      ) {
        const victim = [...prospective.keys()].find(
          (pageId) => !protectedPageIds.has(pageId),
        );
        if (!victim) {
          throw new Error("SGC_ATLAS_BROWSER_WORKING_SET_LIMIT");
        }
        prospective.delete(victim);
        evictions.add(victim);
      }
    }
    if (!isCurrent()) return false;

    const staged = new Map<string, CachedPage>();
    try {
      for (const item of prepared) {
        if (
          this.pages.has(item.page.pageId)
          || removals.has(item.page.pageId)
          || evictions.has(item.page.pageId)
        ) continue;
        staged.set(item.page.pageId, {
          url: this.createUrl(new Blob([item.bytes], { type: item.page.mediaType })),
          bytes: item.bytes.byteLength,
        });
      }
    } catch (error) {
      for (const item of staged.values()) this.revokeUrl(item.url);
      throw error;
    }
    if (!isCurrent()) {
      for (const item of staged.values()) this.revokeUrl(item.url);
      return false;
    }
    for (const pageId of new Set([...removals, ...evictions])) this.remove(pageId);
    for (const [pageId, item] of staged) this.pages.set(pageId, item);
    return true;
  }

  get(pageId: string): string | undefined {
    return this.pages.get(pageId)?.url;
  }

  ids(): string[] {
    return [...this.pages.keys()].sort();
  }

  bytes(): number {
    return [...this.pages.values()].reduce((total, page) => total + page.bytes, 0);
  }

  remove(pageId: string): void {
    const page = this.pages.get(pageId);
    if (!page) return;
    this.revokeUrl(page.url);
    this.pages.delete(pageId);
  }

  clear(): void {
    for (const pageId of this.ids()) this.remove(pageId);
  }
}

export function acquireBrowserAtlasCache(
  componentKey: string,
  create: () => BrowserAtlasCache = () => new BrowserAtlasCache(),
): BrowserAtlasCache {
  let entry = sharedCaches.get(componentKey);
  if (!entry) {
    entry = { cache: create(), leases: 0 };
    sharedCaches.set(componentKey, entry);
  }
  if (entry.releaseTimer !== undefined) {
    clearTimeout(entry.releaseTimer);
    entry.releaseTimer = undefined;
  }
  entry.leases += 1;
  return entry.cache;
}

export function releaseBrowserAtlasCache(componentKey: string): void {
  const entry = sharedCaches.get(componentKey);
  if (!entry) return;
  entry.leases = Math.max(0, entry.leases - 1);
  if (entry.leases > 0 || entry.releaseTimer !== undefined) return;
  entry.releaseTimer = setTimeout(() => {
    const current = sharedCaches.get(componentKey);
    if (current !== entry || current.leases > 0) return;
    current.cache.clear();
    sharedCaches.delete(componentKey);
  }, CACHE_RELEASE_GRACE_MS);
}

export function clearSharedAtlasCachesForTests(): void {
  for (const entry of sharedCaches.values()) {
    if (entry.releaseTimer !== undefined) clearTimeout(entry.releaseTimer);
    entry.cache.clear();
  }
  sharedCaches.clear();
}
