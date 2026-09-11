from __future__ import annotations

import base64
import io

import pytest
from PIL import Image
from streamlit_graph_canvas import (
    AtlasCache,
    AtlasPolicy,
    BadgeBinding,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PaletteTone,
    PngImage,
    Region,
    SpriteBinding,
    SpriteCatalog,
    SpriteRef,
    StaticSprite,
    Transport,
    ValidationError,
    enable_renderers,
    serialize_graph,
)
from streamlit_graph_canvas.atlas import pack_tiles
from streamlit_graph_canvas.sprites import RasterTile


def png(color: tuple[int, int, int, int], size: tuple[int, int] = (8, 8)) -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG")
    return output.getvalue()


def animated_png() -> bytes:
    output = io.BytesIO()
    frames = [
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
        Image.new("RGBA", (8, 8), (0, 0, 255, 255)),
    ]
    frames[0].save(
        output,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=100,
    )
    return output.getvalue()


def schema(*, size: int = 16) -> GraphSchema:
    return GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                sprites=(SpriteBinding("thumbnail", Region.at(2, 3, size, size)),),
            )
        },
        edge_types={},
    )


def graph(*catalog_ids: str) -> GraphData:
    return GraphData(
        tuple(
            Node(
                f"node-{index}",
                "item",
                value,
                sprites={"thumbnail": SpriteRef(value, f"{value} image")},
            )
            for index, value in enumerate(catalog_ids)
        ),
        (),
    )


def crop_color(serialized: object) -> tuple[int, int, int, int]:
    envelope = serialized.envelope  # type: ignore[attr-defined]
    page = envelope["atlas"]["pages"][0]
    location = envelope["presentation"]["nodes"][0]["badges"][0]["sprite"]
    with Image.open(io.BytesIO(base64.b64decode(page["base64"]))) as image:
        return image.getpixel((location["x"], location["y"]))


def test_light_is_default_dark_is_optional_and_falls_back() -> None:
    light = PngImage.from_bytes(png((255, 0, 0, 127)))
    dark = PngImage.from_bytes(png((0, 0, 255, 127)))
    themed = SpriteCatalog({"image": StaticSprite(light, dark)})
    fallback = SpriteCatalog({"image": StaticSprite(light)})
    light_result = serialize_graph(schema(), graph("image"), sprite_catalog=themed)
    dark_result = serialize_graph(
        schema(), graph("image"), sprite_catalog=themed, atlas_theme="dark"
    )
    fallback_result = serialize_graph(
        schema(), graph("image"), sprite_catalog=fallback, atlas_theme="dark"
    )
    assert crop_color(light_result) == (255, 0, 0, 127)
    assert crop_color(dark_result) == (0, 0, 255, 127)
    assert crop_color(fallback_result) == (255, 0, 0, 127)
    assert light_result.topology_hash == dark_result.topology_hash
    assert light_result.presentation_hash != dark_result.presentation_hash


def test_identical_variants_and_nodes_share_one_packed_location() -> None:
    image = PngImage.from_bytes(png((20, 40, 60, 128)))
    catalog = SpriteCatalog({"same": StaticSprite(image, image)})
    result = serialize_graph(
        schema(), graph("same", "same"), sprite_catalog=catalog, atlas_theme="dark"
    )
    layers = [node["badges"][0] for node in result.envelope["presentation"]["nodes"]]
    assert layers[0]["sprite"] == layers[1]["sprite"]
    assert len(result.envelope["atlas"]["pages"]) == 1


def test_multiple_transparent_pngs_are_packed_into_distinct_page_regions() -> None:
    catalog = SpriteCatalog(
        {
            "red": StaticSprite(PngImage.from_bytes(png((255, 0, 0, 90)))),
            "green": StaticSprite(PngImage.from_bytes(png((0, 255, 0, 180)))),
        }
    )
    result = serialize_graph(schema(), graph("red", "green"), sprite_catalog=catalog)
    pages = result.envelope["atlas"]["pages"]
    locations = [
        node["badges"][0]["sprite"] for node in result.envelope["presentation"]["nodes"]
    ]
    assert len(pages) == 1
    assert locations[0]["pageId"] == locations[1]["pageId"]
    assert (locations[0]["x"], locations[0]["y"]) != (
        locations[1]["x"],
        locations[1]["y"],
    )
    with Image.open(io.BytesIO(base64.b64decode(pages[0]["base64"]))) as image:
        colors = {
            image.getpixel((location["x"], location["y"])) for location in locations
        }
    assert colors == {(255, 0, 0, 90), (0, 255, 0, 180)}


def test_adding_a_later_sprite_does_not_move_cached_sprite() -> None:
    cache = AtlasCache(AtlasPolicy())
    catalog = SpriteCatalog(
        {
            "a": StaticSprite(PngImage.from_bytes(png((1, 2, 3, 255)))),
            "b": StaticSprite(PngImage.from_bytes(png((4, 5, 6, 255)))),
        }
    )
    first = serialize_graph(
        schema(), graph("a"), sprite_catalog=catalog, atlas_cache=cache
    )
    before = first.envelope["presentation"]["nodes"][0]["badges"][0]["sprite"]
    known = frozenset(page["pageId"] for page in first.envelope["atlas"]["pages"])
    second = serialize_graph(
        schema(),
        graph("a", "b"),
        sprite_catalog=catalog,
        atlas_cache=cache,
        atlas_known_pages=known,
    )
    after = second.envelope["presentation"]["nodes"][0]["badges"][0]["sprite"]
    assert after == before
    assert len(second.envelope["atlas"]["pages"]) == 1


def test_cached_tenant_page_is_resent_to_a_browser_that_does_not_know_it() -> None:
    cache = AtlasCache(AtlasPolicy())
    catalog = SpriteCatalog(
        {"image": StaticSprite(PngImage.from_bytes(png((1, 2, 3, 255))))}
    )
    first = serialize_graph(
        schema(), graph("image"), sprite_catalog=catalog, atlas_cache=cache
    )
    second_browser = serialize_graph(
        schema(), graph("image"), sprite_catalog=catalog, atlas_cache=cache
    )
    assert second_browser.envelope["atlas"]["pages"] == first.envelope["atlas"]["pages"]


def test_static_and_prims_raster_tiles_share_a_real_page() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    mixed_schema = GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                badges=(
                    BadgeBinding(
                        "count",
                        "streamlit-graph-canvas/contrib/count-chip",
                        Region.at(0, 0, 42, 22),
                        transport=Transport.RASTER,
                    ),
                ),
                sprites=(SpriteBinding("thumbnail", Region.at(50, 0, 16, 16)),),
            )
        },
        edge_types={},
        palette={
            "accent": PaletteTone("#2563eb", "#60a5fa"),
            "on_accent": PaletteTone("#ffffff", "#0f172a"),
        },
    )
    mixed_graph = GraphData(
        (
            Node(
                "a",
                "item",
                "A",
                badges={"count": 7},
                sprites={"thumbnail": SpriteRef("image")},
            ),
        ),
        (),
    )
    result = serialize_graph(
        mixed_schema,
        mixed_graph,
        renderer_registry=registry,
        sprite_catalog=SpriteCatalog(
            {"image": StaticSprite(PngImage.from_bytes(png((8, 9, 10, 128))))}
        ),
    )
    layers = result.envelope["presentation"]["nodes"][0]["badges"]
    assert layers[0]["sprite"]["pageId"] == layers[1]["sprite"]["pageId"]
    assert len(result.envelope["atlas"]["pages"]) == 1


def test_paths_and_source_bytes_never_cross_the_envelope(tmp_path: object) -> None:
    path = tmp_path / "private-name.png"  # type: ignore[operator]
    path.write_bytes(png((10, 20, 30, 255)))
    catalog = SpriteCatalog({"safe-id": StaticSprite(PngImage.from_file(path))})
    result = serialize_graph(schema(), graph("safe-id"), sprite_catalog=catalog)
    encoded = str(result.envelope)
    assert "private-name.png" not in encoded
    assert str(path) not in encoded


@pytest.mark.parametrize(
    "content",
    [b"not png", png((1, 2, 3, 4))[:-8]],
)
def test_invalid_or_truncated_png_fails_closed(content: bytes) -> None:
    catalog = SpriteCatalog({"bad": StaticSprite(PngImage.from_bytes(content))})
    with pytest.raises(ValidationError, match="SGC_SPRITE_PNG"):
        serialize_graph(schema(), graph("bad"), sprite_catalog=catalog)


def test_catalog_is_required_and_catalog_ids_are_authoritative() -> None:
    with pytest.raises(ValidationError, match="SGC_SPRITE_CATALOG_REQUIRED"):
        serialize_graph(schema(), graph("missing"))
    with pytest.raises(ValidationError, match="SGC_SPRITE_CATALOG_MISSING"):
        serialize_graph(schema(), graph("missing"), sprite_catalog=SpriteCatalog({}))


def test_animated_png_and_reviewed_source_limits_fail_closed() -> None:
    animated = SpriteCatalog(
        {"animated": StaticSprite(PngImage.from_bytes(animated_png()))}
    )
    with pytest.raises(ValidationError, match="SGC_SPRITE_PNG_FORMAT"):
        serialize_graph(schema(), graph("animated"), sprite_catalog=animated)
    oversized = SpriteCatalog(
        {"large": StaticSprite(PngImage.from_bytes(png((1, 2, 3, 4), (9, 9))))}
    )
    with pytest.raises(ValidationError, match="SGC_SPRITE_SOURCE_DIMENSIONS"):
        serialize_graph(
            schema(),
            graph("large"),
            sprite_catalog=oversized,
            atlas_policy=AtlasPolicy(max_source_decoded_pixels=64),
        )


def test_static_page_ids_are_tenant_isolated() -> None:
    catalog = SpriteCatalog(
        {"image": StaticSprite(PngImage.from_bytes(png((1, 2, 3, 128))))}
    )
    cache = AtlasCache(AtlasPolicy())
    left = serialize_graph(
        schema(),
        graph("image"),
        sprite_catalog=catalog,
        atlas_cache=cache,
        atlas_tenant="left",
    )
    right = serialize_graph(
        schema(),
        graph("image"),
        sprite_catalog=catalog,
        atlas_cache=cache,
        atlas_tenant="right",
    )
    left_page = left.envelope["presentation"]["nodes"][0]["badges"][0]["sprite"][
        "pageId"
    ]
    right_page = right.envelope["presentation"]["nodes"][0]["badges"][0]["sprite"][
        "pageId"
    ]
    assert left_page != right_page


def test_packing_is_deterministic_in_bounds_and_non_overlapping() -> None:
    policy = AtlasPolicy(page_width=64, page_height=64)
    tiles = (
        RasterTile("b", png((0, 255, 0, 255), (15, 10)), 15, 10),
        RasterTile("a", png((255, 0, 0, 255), (20, 12)), 20, 12),
        RasterTile("c", png((0, 0, 255, 255), (9, 18)), 9, 18),
    )
    forward = pack_tiles(tiles, policy=policy, subject="test")
    reverse = pack_tiles(tuple(reversed(tiles)), policy=policy, subject="test")
    assert [page.content for page, _ in forward] == [
        page.content for page, _ in reverse
    ]
    assert [locations for _, locations in forward] == [
        locations for _, locations in reverse
    ]
    for page, locations in forward:
        assert page.width == 64 and page.height == 64
        rectangles = list(locations.values())
        for location in rectangles:
            assert location.x >= policy.padding
            assert location.y >= policy.padding
            assert location.x + location.width < page.width
            assert location.y + location.height < page.height
        for index, left in enumerate(rectangles):
            for right in rectangles[index + 1 :]:
                assert (
                    left.x + left.width <= right.x
                    or right.x + right.width <= left.x
                    or left.y + left.height <= right.y
                    or right.y + right.height <= left.y
                )


def test_active_working_set_failure_is_atomic_and_eviction_removes_mapping() -> None:
    policy = AtlasPolicy(
        max_pages=1,
        max_tenant_pages=1,
        page_width=24,
        page_height=24,
    )
    cache = AtlasCache(policy)
    first_tile = RasterTile("a", png((1, 2, 3, 255), (20, 20)), 20, 20)
    second_tile = RasterTile("b", png((4, 5, 6, 255), (20, 20)), 20, 20)
    first = cache.resolve_tiles(tenant="session", tiles={"a": first_tile})
    second = cache.resolve_tiles(tenant="session", tiles={"b": second_tile})
    assert first.locations["a"].page_id in second.evicted_page_ids
    before = cache.snapshot()
    with pytest.raises(ValidationError, match="SGC_ATLAS_WORKING_SET_LIMIT"):
        cache.resolve_tiles(tenant="session", tiles={"a": first_tile, "b": second_tile})
    assert cache.snapshot() == before
    restored = cache.resolve_tiles(tenant="session", tiles={"a": first_tile})
    assert restored.added_pages
