from __future__ import annotations

import io
import struct
import zlib

import pytest
from PIL import Image, PngImagePlugin
from streamlit_graph_canvas import (
    AtlasPolicy,
    PngImage,
    SpriteCatalog,
    StaticSprite,
    ValidationError,
)
from streamlit_graph_canvas.images import (
    HARD_MAX_SOURCE_BYTES,
    MAX_CATALOG_ID_CHARS,
    normalize_catalog,
    normalize_png,
)


def png(
    color: tuple[int, int, int, int] = (1, 2, 3, 255),
    size: tuple[int, int] = (8, 8),
    **save: object,
) -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG", **save)
    return output.getvalue()


def chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def with_ihdr_size(content: bytes, width: int, height: int) -> bytes:
    """Rewrite IHDR dimensions with a valid CRC, leaving image data untouched."""
    ihdr = bytearray(content[16:29])
    ihdr[0:8] = struct.pack(">II", width, height)
    return content[:8] + chunk(b"IHDR", bytes(ihdr)) + content[33:]


def code_of(
    content: bytes, policy: AtlasPolicy | None = None, subject: str = "sprite"
) -> str:
    with pytest.raises(ValidationError) as error:
        normalize_png(
            PngImage.from_bytes(content),
            policy=policy or AtlasPolicy(),
            subject=subject,
        )
    assert error.value.diagnostic.subject == subject
    return error.value.diagnostic.code


@pytest.mark.parametrize(
    "content",
    [
        b"not png",
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,
        png()[:-12],
        png().replace(b"IHDR", b"IHDX", 1),
        png()[:8] + struct.pack(">I", 14) + png()[12:],
    ],
    ids=["text", "signature-only", "missing-iend", "wrong-chunk", "ihdr-length"],
)
def test_structurally_invalid_png_fails_signature_check(content: bytes) -> None:
    assert code_of(content) == "SGC_SPRITE_PNG_SIGNATURE"


def test_corrupt_image_data_fails_decode_without_leaking_pillow_errors() -> None:
    original = png(size=(16, 16))
    idat = original.index(b"IDAT")
    length = struct.unpack(">I", original[idat - 4 : idat])[0]
    data = original[idat + 4 : idat + 4 + length]
    truncated = original[: idat - 4] + chunk(b"IDAT", data[: len(data) // 2])
    truncated += original[original.index(b"IEND") - 4 :]
    assert code_of(truncated) == "SGC_SPRITE_PNG_DECODE"


def test_corrupt_zlib_stream_fails_decode() -> None:
    original = bytearray(png())
    idat = original.index(b"IDAT")
    original[idat + 4] ^= 0xFF
    assert code_of(bytes(original)) == "SGC_SPRITE_PNG_DECODE"


def test_bad_header_crc_fails_decode() -> None:
    original = bytearray(png())
    # IHDR CRC follows the 4-byte length, 4-byte type, and 13-byte payload.
    original[29] ^= 0xFF
    assert code_of(bytes(original)) == "SGC_SPRITE_PNG_DECODE"


@pytest.mark.parametrize("limit", [20, 40])
def test_pillow_decompression_bomb_guard_is_a_diagnostic(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    # 8x8 = 64 pixels: above 2*20 raises the bomb error, above 40 the warning.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", limit)
    assert code_of(png()) == "SGC_SPRITE_DECOMPRESSION_BOMB"


def test_source_byte_limit_is_checked_before_decoding() -> None:
    content = png()
    policy = AtlasPolicy(max_source_bytes=len(content) - 1)
    assert code_of(content, policy) == "SGC_SPRITE_SOURCE_BYTES"
    assert (
        normalize_png(
            PngImage.from_bytes(content),
            policy=AtlasPolicy(max_source_bytes=len(content)),
            subject="sprite",
        ).width
        == 8
    )


@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 8), (8, 0), (4097, 1), (1, 4097), (60_000, 60_000)],
)
def test_declared_dimensions_are_bounded_before_decoding(
    width: int, height: int
) -> None:
    content = with_ihdr_size(png(), width, height)
    assert code_of(content) == "SGC_SPRITE_SOURCE_DIMENSIONS"


def test_normalization_strips_metadata_and_is_deterministic() -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "private author note")
    plain = png(compress_level=1)
    annotated = png(pnginfo=info, compress_level=9)
    policy = AtlasPolicy()
    first = normalize_png(PngImage.from_bytes(plain), policy=policy, subject="a")
    second = normalize_png(PngImage.from_bytes(annotated), policy=policy, subject="b")
    assert first == second
    assert b"private author note" not in second.content
    assert (first.width, first.height) == (8, 8)
    with Image.open(io.BytesIO(first.content)) as decoded:
        assert decoded.mode == "RGBA"


def test_palette_images_are_canonicalized_to_rgba() -> None:
    output = io.BytesIO()
    Image.new("P", (4, 4), 0).save(output, format="PNG")
    normalized = normalize_png(
        PngImage.from_bytes(output.getvalue()), policy=AtlasPolicy(), subject="p"
    )
    with Image.open(io.BytesIO(normalized.content)) as decoded:
        assert decoded.mode == "RGBA"


def catalog(count: int, content: bytes | None = None) -> SpriteCatalog:
    image = PngImage.from_bytes(content or png())
    return SpriteCatalog({f"s{i}": StaticSprite(image, image) for i in range(count)})


def test_catalog_entry_limit() -> None:
    assert normalize_catalog(catalog(2), policy=AtlasPolicy(max_catalog_entries=2))
    with pytest.raises(ValidationError, match="SGC_SPRITE_CATALOG_ENTRIES"):
        normalize_catalog(catalog(3), policy=AtlasPolicy(max_catalog_entries=2))


def test_catalog_aggregate_byte_limit_counts_dark_variants() -> None:
    size = len(png())
    # Two entries x (light + dark) = four encoded sources.
    assert normalize_catalog(catalog(2), policy=AtlasPolicy(max_catalog_bytes=4 * size))
    with pytest.raises(ValidationError, match="SGC_SPRITE_CATALOG_BYTES"):
        normalize_catalog(
            catalog(2), policy=AtlasPolicy(max_catalog_bytes=4 * size - 1)
        )


def test_catalog_declared_pixel_limit_is_checked_before_any_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit_graph_canvas.images as images

    def never(*_: object, **__: object) -> None:
        raise AssertionError("catalog limits must be enforced before decoding")

    monkeypatch.setattr(images, "normalize_png", never)
    # Four 8x8 sources declare 256 pixels.
    with pytest.raises(ValidationError, match="SGC_SPRITE_CATALOG_PIXELS"):
        normalize_catalog(
            catalog(2), policy=AtlasPolicy(max_catalog_decoded_pixels=255)
        )


def test_catalog_with_one_bad_entry_fails_with_that_entry_as_subject() -> None:
    sprites = {
        "good": StaticSprite(PngImage.from_bytes(png())),
        "bad": StaticSprite(PngImage.from_bytes(b"not png")),
    }
    with pytest.raises(ValidationError) as error:
        normalize_catalog(SpriteCatalog(sprites), policy=AtlasPolicy())
    assert error.value.diagnostic.code == "SGC_SPRITE_PNG_SIGNATURE"
    assert error.value.diagnostic.subject == "bad"


@pytest.mark.parametrize(
    "key", ["", " padded", "padded ", "x" * (MAX_CATALOG_ID_CHARS + 1), 7, None]
)
def test_catalog_ids_are_trimmed_bounded_strings(key: object) -> None:
    with pytest.raises(ValueError, match="SpriteCatalog IDs"):
        SpriteCatalog({key: StaticSprite(PngImage.from_bytes(png()))})  # type: ignore[dict-item]


def test_catalog_values_must_be_static_sprites_and_mapping_is_read_only() -> None:
    with pytest.raises(TypeError):
        SpriteCatalog({"raw": PngImage.from_bytes(png())})  # type: ignore[dict-item]
    built = SpriteCatalog({"x" * MAX_CATALOG_ID_CHARS: StaticSprite(PngImage(png()))})
    with pytest.raises(TypeError):
        built.sprites["y"] = StaticSprite(PngImage(png()))  # type: ignore[index]


def test_png_image_rejects_empty_non_bytes_and_oversized_content(tmp_path) -> None:
    with pytest.raises(ValueError):
        PngImage(b"")
    with pytest.raises(TypeError):
        PngImage(bytearray(png()))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PngImage(b"\x00" * (HARD_MAX_SOURCE_BYTES + 1))
    large = tmp_path / "large.png"
    large.write_bytes(b"\x00" * (HARD_MAX_SOURCE_BYTES + 1))
    with pytest.raises(ValueError, match="hard encoded-byte limit"):
        PngImage.from_file(large)
    with pytest.raises(ValueError, match="could not be read"):
        PngImage.from_file(tmp_path / "missing.png")


def test_static_sprite_theme_selection() -> None:
    light, dark = PngImage(png((1, 1, 1, 255))), PngImage(png((2, 2, 2, 255)))
    assert StaticSprite(light, dark).select("dark") is dark
    assert StaticSprite(light).select("dark") is light
    with pytest.raises(ValueError):
        StaticSprite(light).select("sepia")
    with pytest.raises(TypeError):
        StaticSprite(light, dark=png())  # type: ignore[arg-type]
