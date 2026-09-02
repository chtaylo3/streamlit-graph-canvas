import type { AtlasPageDescriptor } from "./atlas-cache";

export type SpriteLocation = {
  pageId: string;
  x: number;
  y: number;
  width: number;
  height: number;
  resolution: 1 | 1.5 | 2;
};

export type ImageLayer = {
  transport: "raster" | "atlas" | "sprite";
  atlas?: unknown;
  sprite?: unknown;
};

export type LogicalRegion = { width: number; height: number };

const SHA256 = /^[0-9a-f]{64}$/;
const LOCATION_FIELDS = [
  "height",
  "pageId",
  "resolution",
  "width",
  "x",
  "y",
].sort();

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function imageLayerLocation(layer: ImageLayer): unknown {
  if ((layer.sprite === undefined) === (layer.atlas === undefined)) {
    throw new Error(
      "SGC_SPRITE_LOCATION_FIELD: image layer must supply exactly one location field",
    );
  }
  return layer.sprite ?? layer.atlas;
}

export function validateSpriteLocation(
  value: unknown,
  page: AtlasPageDescriptor | undefined,
  region?: LogicalRegion,
): SpriteLocation {
  if (
    !isRecord(value)
    || JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(LOCATION_FIELDS)
    || typeof value.pageId !== "string"
    || !SHA256.test(value.pageId)
    || !Number.isSafeInteger(value.x)
    || !Number.isSafeInteger(value.y)
    || !Number.isSafeInteger(value.width)
    || !Number.isSafeInteger(value.height)
    || (value.resolution !== 1 && value.resolution !== 1.5 && value.resolution !== 2)
  ) {
    throw new Error("SGC_SPRITE_LOCATION_SHAPE: sprite location is invalid");
  }
  const location = value as SpriteLocation;
  if (
    location.x < 0
    || location.y < 0
    || location.width <= 0
    || location.height <= 0
  ) {
    throw new Error("SGC_SPRITE_LOCATION_BOUNDS: sprite rectangle is invalid");
  }
  if (!page) {
    throw new Error("SGC_SPRITE_PAGE_MISSING: sprite atlas page is unavailable");
  }
  if (
    location.x > page.width - location.width
    || location.y > page.height - location.height
  ) {
    throw new Error("SGC_SPRITE_LOCATION_BOUNDS: sprite exceeds its atlas page");
  }
  if (region) {
    const widthDelta = Math.abs(
      location.width - region.width * location.resolution,
    );
    const heightDelta = Math.abs(
      location.height - region.height * location.resolution,
    );
    const widthIsMinimumPixel = location.width === 1
      && region.width * location.resolution < 1;
    const heightIsMinimumPixel = location.height === 1
      && region.height * location.resolution < 1;
    if (
      (!widthIsMinimumPixel && widthDelta > 0.500000001)
      || (!heightIsMinimumPixel && heightDelta > 0.500000001)
    ) {
      throw new Error(
        "SGC_SPRITE_LOGICAL_SIZE: sprite dimensions do not match its logical region",
      );
    }
  }
  return location;
}

export function spriteCrop(
  location: SpriteLocation,
  page: AtlasPageDescriptor,
): {
  viewBox: string;
  imageWidth: number;
  imageHeight: number;
  logicalWidth: number;
  logicalHeight: number;
} {
  return {
    viewBox: `${location.x} ${location.y} ${location.width} ${location.height}`,
    imageWidth: page.width,
    imageHeight: page.height,
    logicalWidth: location.width / location.resolution,
    logicalHeight: location.height / location.resolution,
  };
}
