"""Bounded, deterministic ingestion of application-provided PNG sprites."""

from __future__ import annotations

import hashlib
import io
import struct
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from .contract import MAX_SPRITE_SOURCE_BYTES
from .errors import Diagnostic, ValidationError

if TYPE_CHECKING:
    from .atlas import AtlasPolicy

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"
PNG_NORMALIZER_REVISION = 1
MAX_CATALOG_ID_CHARS = 128
HARD_MAX_SOURCE_BYTES = MAX_SPRITE_SOURCE_BYTES


def _fail(code: str, message: str, action: str, subject: str) -> ValidationError:
    return ValidationError(Diagnostic(code, message, action, subject))


@dataclass(frozen=True, slots=True)
class PngImage:
    """Immutable PNG bytes owned by the application process."""

    content: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise TypeError("PngImage content must be bytes")
        if not self.content:
            raise ValueError("PngImage content cannot be empty")
        if len(self.content) > HARD_MAX_SOURCE_BYTES:
            raise ValueError("PngImage exceeds the reviewed hard encoded-byte limit")

    @classmethod
    def from_bytes(cls, content: bytes | bytearray | memoryview) -> PngImage:
        return cls(bytes(content))

    @classmethod
    def from_file(cls, path: str | Path) -> PngImage:
        """Read a trusted server path immediately without retaining the path."""

        try:
            with Path(path).open("rb") as source:
                content = source.read(HARD_MAX_SOURCE_BYTES + 1)
        except OSError:
            raise ValueError("PNG file could not be read") from None
        if len(content) > HARD_MAX_SOURCE_BYTES:
            raise ValueError("PNG file exceeds the reviewed hard encoded-byte limit")
        return cls(content)


@dataclass(frozen=True, slots=True)
class StaticSprite:
    """Light/default image with an optional dark-theme variant."""

    light: PngImage
    dark: PngImage | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.light, PngImage):
            raise TypeError("StaticSprite.light must be a PngImage")
        if self.dark is not None and not isinstance(self.dark, PngImage):
            raise TypeError("StaticSprite.dark must be a PngImage or None")

    def select(self, theme: str) -> PngImage:
        if theme not in {"light", "dark"}:
            raise ValueError("theme must be 'light' or 'dark'")
        return self.dark if theme == "dark" and self.dark is not None else self.light


class SpriteCatalog:
    """Immutable mapping from stable application IDs to static sprites."""

    __slots__ = ("_sprites",)

    def __init__(self, sprites: Mapping[str, StaticSprite]) -> None:
        copied: dict[str, StaticSprite] = {}
        for key, sprite in sprites.items():
            if (
                not isinstance(key, str)
                or not key
                or key != key.strip()
                or len(key) > MAX_CATALOG_ID_CHARS
            ):
                raise ValueError(
                    "SpriteCatalog IDs must be non-empty trimmed strings of at most "
                    f"{MAX_CATALOG_ID_CHARS} characters"
                )
            if not isinstance(sprite, StaticSprite):
                raise TypeError("SpriteCatalog values must be StaticSprite instances")
            if key in copied:
                raise ValueError(f"duplicate SpriteCatalog ID {key!r}")
            copied[key] = sprite
        self._sprites = MappingProxyType(copied)

    @property
    def sprites(self) -> Mapping[str, StaticSprite]:
        return self._sprites

    def __len__(self) -> int:
        return len(self._sprites)

    def __contains__(self, key: object) -> bool:
        return key in self._sprites

    def __getitem__(self, key: str) -> StaticSprite:
        return self._sprites[key]


@dataclass(frozen=True, slots=True)
class NormalizedPng:
    content: bytes
    width: int
    height: int
    content_hash: str


def _ihdr_dimensions(content: bytes, *, subject: str) -> tuple[int, int]:
    if (
        len(content) < 33
        or not content.startswith(PNG_SIGNATURE)
        or content[12:16] != b"IHDR"
        or struct.unpack(">I", content[8:12])[0] != 13
        or not content.endswith(PNG_IEND)
    ):
        raise _fail(
            "SGC_SPRITE_PNG_SIGNATURE",
            "Static sprite data is not a supported PNG.",
            "Provide a complete, static PNG image.",
            subject,
        )
    width, height = struct.unpack(">II", content[16:24])
    return width, height


def normalize_png(
    image: PngImage, *, policy: AtlasPolicy, subject: str
) -> NormalizedPng:
    """Decode, canonicalize to RGBA, strip metadata, and deterministically encode."""

    content = image.content
    from .atlas import pillow_rasterizer_version

    pillow_rasterizer_version(subject=subject)
    if len(content) > policy.max_source_bytes:
        raise _fail(
            "SGC_SPRITE_SOURCE_BYTES",
            "Static sprite exceeds the configured encoded-byte limit.",
            "Reduce the image or increase the reviewed source-image limit.",
            subject,
        )
    width, height = _ihdr_dimensions(content, subject=subject)
    if (
        width <= 0
        or height <= 0
        or width > policy.max_source_dimension
        or height > policy.max_source_dimension
        or width * height > policy.max_source_decoded_pixels
    ):
        raise _fail(
            "SGC_SPRITE_SOURCE_DIMENSIONS",
            "Static sprite dimensions exceed the configured decoded-pixel limits.",
            "Resize the source image or increase the reviewed image limits.",
            subject,
        )
    from PIL import Image, UnidentifiedImageError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as opened:
                if opened.format != "PNG" or getattr(opened, "n_frames", 1) != 1:
                    raise _fail(
                        "SGC_SPRITE_PNG_FORMAT",
                        "Static sprites must be single-frame PNG images.",
                        "Convert the source to a static PNG.",
                        subject,
                    )
                opened.load()
                rgba = opened.convert("RGBA")
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise _fail(
            "SGC_SPRITE_DECOMPRESSION_BOMB",
            "Static sprite triggered Pillow's decompression-bomb protection.",
            "Use a smaller trusted PNG image.",
            subject,
        ) from error
    except (OSError, SyntaxError, UnidentifiedImageError) as error:
        raise _fail(
            "SGC_SPRITE_PNG_DECODE",
            "Static sprite PNG is malformed or truncated.",
            "Provide a complete, valid PNG image.",
            subject,
        ) from error
    output = io.BytesIO()
    rgba.save(output, format="PNG", optimize=False, compress_level=9)
    normalized = output.getvalue()
    identity = hashlib.sha256()
    identity.update(f"sgc-png-v{PNG_NORMALIZER_REVISION}:{width}x{height}:".encode())
    identity.update(normalized)
    return NormalizedPng(normalized, width, height, identity.hexdigest())


def normalize_catalog(
    catalog: SpriteCatalog, *, policy: AtlasPolicy
) -> dict[str, dict[str, NormalizedPng]]:
    """Validate the complete light/dark working set before serialization."""

    if len(catalog) > policy.max_catalog_entries:
        raise _fail(
            "SGC_SPRITE_CATALOG_ENTRIES",
            "Sprite catalog exceeds the configured entry limit.",
            "Reduce the catalog or increase the reviewed entry limit.",
            "sprite catalog",
        )
    encoded_bytes = sum(
        len(source.content)
        for sprite in catalog.sprites.values()
        for source in (sprite.light, sprite.dark)
        if source is not None
    )
    if encoded_bytes > policy.max_catalog_bytes:
        raise _fail(
            "SGC_SPRITE_CATALOG_BYTES",
            "Sprite catalog exceeds the configured aggregate encoded-byte limit.",
            "Reduce the catalog or increase the reviewed aggregate limit.",
            "sprite catalog",
        )
    declared_pixels = 0
    for key, sprite in catalog.sprites.items():
        for source in (sprite.light, sprite.dark):
            if source is None:
                continue
            width, height = _ihdr_dimensions(source.content, subject=key)
            declared_pixels += width * height
    if declared_pixels > policy.max_catalog_decoded_pixels:
        raise _fail(
            "SGC_SPRITE_CATALOG_PIXELS",
            "Sprite catalog exceeds the configured aggregate decoded-pixel limit.",
            "Reduce the catalog or increase the reviewed aggregate limit.",
            "sprite catalog",
        )
    decoded_pixels = 0
    result: dict[str, dict[str, NormalizedPng]] = {}
    for key, sprite in catalog.sprites.items():
        variants: dict[str, NormalizedPng] = {}
        for theme, source in (("light", sprite.light), ("dark", sprite.dark)):
            if source is None:
                continue
            normalized = normalize_png(source, policy=policy, subject=key)
            decoded_pixels += normalized.width * normalized.height
            variants[theme] = normalized
        result[key] = variants
    if decoded_pixels > policy.max_catalog_decoded_pixels:
        raise _fail(
            "SGC_SPRITE_CATALOG_PIXELS",
            "Sprite catalog exceeds the configured aggregate decoded-pixel limit.",
            "Reduce the catalog or increase the reviewed aggregate limit.",
            "sprite catalog",
        )
    return result
