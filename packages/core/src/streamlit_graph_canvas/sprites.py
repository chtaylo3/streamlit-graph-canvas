"""Public sprite bindings and internal prepared raster tiles."""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from typing import Literal

from .atlas import AtlasPolicy, pillow_rasterizer_version
from .errors import Diagnostic, ValidationError
from .images import MAX_CATALOG_ID_CHARS, NormalizedPng
from .model import Region

SpriteFit = Literal["contain", "cover", "fill"]


@dataclass(frozen=True, slots=True)
class SpriteBinding:
    name: str
    region: Region
    layer: Literal["under", "over"] = "over"
    z: int = 0
    fit: SpriteFit = "contain"
    required: bool = False

    def __post_init__(self) -> None:
        if self.fit not in {"contain", "cover", "fill"}:
            raise ValueError("SpriteBinding.fit must be contain, cover, or fill")


@dataclass(frozen=True, slots=True)
class SpriteRef:
    catalog_id: str
    accessible_text: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.catalog_id, str)
            or not self.catalog_id
            or self.catalog_id != self.catalog_id.strip()
            or len(self.catalog_id) > MAX_CATALOG_ID_CHARS
        ):
            raise ValueError(
                "SpriteRef.catalog_id must be a trimmed string of at most "
                f"{MAX_CATALOG_ID_CHARS} characters"
            )
        if self.accessible_text is not None and (
            not isinstance(self.accessible_text, str)
            or not self.accessible_text.strip()
            or len(self.accessible_text) > 512
        ):
            raise ValueError(
                "SpriteRef.accessible_text must be a non-empty string of at most "
                "512 characters"
            )


@dataclass(frozen=True, slots=True)
class RasterTile:
    content_key: str
    content: bytes
    width: int
    height: int


def prepare_static_tile(
    source: NormalizedPng,
    *,
    logical_width: float,
    logical_height: float,
    resolution: float,
    fit: SpriteFit,
    policy: AtlasPolicy,
    subject: str,
) -> RasterTile:
    """Apply fit and DPR to a normalized source before atlas packing."""

    pixel_width = max(1, round(logical_width * resolution))
    pixel_height = max(1, round(logical_height * resolution))
    if pixel_width * pixel_height > policy.max_prepared_tile_pixels:
        raise ValidationError(
            Diagnostic(
                "SGC_SPRITE_TILE_PIXELS",
                "Prepared sprite exceeds the configured decoded-pixel limit.",
                "Reduce the binding region, resolution, or reviewed tile limit.",
                subject,
            )
        )
    key = static_tile_content_key(
        source,
        logical_width=logical_width,
        logical_height=logical_height,
        resolution=resolution,
        fit=fit,
        subject=subject,
    )
    from PIL import Image

    with Image.open(io.BytesIO(source.content)) as opened:
        image = opened.convert("RGBA")
    if fit == "fill":
        prepared = image.resize((pixel_width, pixel_height), Image.Resampling.LANCZOS)
    else:
        source_ratio = image.width / image.height
        target_ratio = pixel_width / pixel_height
        if fit == "contain":
            if source_ratio >= target_ratio:
                width = pixel_width
                height = max(1, round(width / source_ratio))
            else:
                height = pixel_height
                width = max(1, round(height * source_ratio))
            resized = image.resize((width, height), Image.Resampling.LANCZOS)
            prepared = Image.new("RGBA", (pixel_width, pixel_height), (0, 0, 0, 0))
            prepared.alpha_composite(
                resized, ((pixel_width - width) // 2, (pixel_height - height) // 2)
            )
        else:
            if source_ratio >= target_ratio:
                height = pixel_height
                width = max(1, math.ceil(height * source_ratio))
            else:
                width = pixel_width
                height = max(1, math.ceil(width / source_ratio))
            resized = image.resize((width, height), Image.Resampling.LANCZOS)
            left = max(0, (width - pixel_width) // 2)
            top = max(0, (height - pixel_height) // 2)
            prepared = resized.crop((left, top, left + pixel_width, top + pixel_height))
    output = io.BytesIO()
    prepared.save(output, format="PNG", optimize=False, compress_level=9)
    return RasterTile(key, output.getvalue(), pixel_width, pixel_height)


def static_tile_content_key(
    source: NormalizedPng,
    *,
    logical_width: float,
    logical_height: float,
    resolution: float,
    fit: SpriteFit,
    subject: str,
) -> str:
    """Return the prepared-tile identity without performing image resampling."""

    payload = {
        "source": source.content_hash,
        "width": logical_width,
        "height": logical_height,
        "resolution": resolution,
        "fit": fit,
        "rasterizer": pillow_rasterizer_version(subject=subject),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
