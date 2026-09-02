import { describe, expect, it } from "vitest";
import type { AtlasPageDescriptor } from "./atlas-cache";
import {
  imageLayerLocation,
  spriteCrop,
  validateSpriteLocation,
  type SpriteLocation,
} from "./sprite-location";

const PAGE: AtlasPageDescriptor = {
  url: "blob:page",
  bytes: 1024,
  width: 512,
  height: 256,
};
const LOCATION: SpriteLocation = {
  pageId: "a".repeat(64),
  x: 128,
  y: 32,
  width: 144,
  height: 96,
  resolution: 1.5,
};

describe("sprite atlas locations", () => {
  it("accepts packed, nonzero coordinates fully inside the page", () => {
    expect(validateSpriteLocation(LOCATION, PAGE)).toEqual(LOCATION);
  });

  it.each([
    ["negative x", { x: -1 }, "SGC_SPRITE_LOCATION_BOUNDS"],
    ["fractional y", { y: 0.5 }, "SGC_SPRITE_LOCATION_SHAPE"],
    ["zero width", { width: 0 }, "SGC_SPRITE_LOCATION_BOUNDS"],
    ["unsafe height", { height: Number.MAX_SAFE_INTEGER + 1 }, "SGC_SPRITE_LOCATION_SHAPE"],
    ["unsupported resolution", { resolution: 3 }, "SGC_SPRITE_LOCATION_SHAPE"],
    ["right overflow", { x: 500 }, "SGC_SPRITE_LOCATION_BOUNDS"],
    ["bottom overflow", { y: 200 }, "SGC_SPRITE_LOCATION_BOUNDS"],
    ["invalid page id", { pageId: "page" }, "SGC_SPRITE_LOCATION_SHAPE"],
  ])("rejects %s", (_name, update, diagnostic) => {
    expect(() => validateSpriteLocation({ ...LOCATION, ...update }, PAGE)).toThrow(
      diagnostic,
    );
  });

  it("rejects a location whose page is not installed", () => {
    expect(() => validateSpriteLocation(LOCATION, undefined)).toThrow(
      "SGC_SPRITE_PAGE_MISSING",
    );
  });

  it("accepts server rounding but rejects DPR dimensions that distort the region", () => {
    expect(() => validateSpriteLocation(
      LOCATION,
      PAGE,
      { width: 96.2, height: 63.8 },
    )).not.toThrow();
    expect(() => validateSpriteLocation(
      { ...LOCATION, width: 145 },
      PAGE,
      { width: 96, height: 64 },
    )).toThrow("SGC_SPRITE_LOGICAL_SIZE");
    expect(() => validateSpriteLocation(
      { ...LOCATION, height: 97 },
      PAGE,
      { width: 96, height: 64 },
    )).toThrow("SGC_SPRITE_LOGICAL_SIZE");
  });

  it("uses the complete atlas page with a crop viewBox and DPR logical size", () => {
    expect(spriteCrop(LOCATION, PAGE)).toEqual({
      viewBox: "128 32 144 96",
      imageWidth: 512,
      imageHeight: 256,
      logicalWidth: 96,
      logicalHeight: 64,
    });
  });

  it.each([
    [1 as const, 96, 64],
    [1.5 as const, 144, 96],
    [2 as const, 192, 128],
  ])("keeps the same logical dimensions at %sx", (resolution, width, height) => {
    const crop = spriteCrop(
      { ...LOCATION, width, height, resolution },
      PAGE,
    );
    expect([crop.logicalWidth, crop.logicalHeight]).toEqual([96, 64]);
  });

  it("accepts sprite and legacy atlas location fields", () => {
    expect(imageLayerLocation({ transport: "sprite", sprite: LOCATION })).toBe(LOCATION);
    expect(imageLayerLocation({ transport: "raster", atlas: LOCATION })).toBe(LOCATION);
    expect(imageLayerLocation({ transport: "atlas", atlas: LOCATION })).toBe(LOCATION);
  });

  it("rejects missing or ambiguous location fields", () => {
    expect(() => imageLayerLocation({ transport: "sprite" })).toThrow(
      "SGC_SPRITE_LOCATION_FIELD",
    );
    expect(() => imageLayerLocation({
      transport: "sprite",
      sprite: LOCATION,
      atlas: LOCATION,
    })).toThrow("SGC_SPRITE_LOCATION_FIELD");
  });
});
