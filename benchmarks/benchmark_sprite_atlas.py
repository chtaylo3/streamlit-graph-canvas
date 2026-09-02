"""Record representative static-sprite atlas packing and rerun evidence."""

from __future__ import annotations

import io
import json
import time

from PIL import Image, ImageDraw
from streamlit_graph_canvas import (
    AtlasCache,
    AtlasPolicy,
    GraphData,
    GraphSchema,
    Node,
    NodeType,
    PngImage,
    Region,
    SpriteBinding,
    SpriteCatalog,
    SpriteRef,
    StaticSprite,
    serialize_graph,
)

NODE_COUNT = 500
UNIQUE_IMAGE_COUNT = 100


def _image(index: int) -> PngImage:
    canvas = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    color = ((index * 47) % 256, (index * 83) % 256, (index * 131) % 256, 210)
    draw.ellipse((4, 4, 67, 67), fill=color)
    draw.text((28, 28), str(index % 10), fill=(255, 255, 255, 255))
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=False, compress_level=9)
    return PngImage.from_bytes(output.getvalue())


def _serialize(
    graph: GraphData, catalog: SpriteCatalog, cache: AtlasCache, known: frozenset[str]
) -> tuple[object, float]:
    schema = GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                sprites=(SpriteBinding("thumbnail", Region.at(4, 4, 72, 72)),),
            )
        },
        edge_types={},
    )
    started = time.perf_counter()
    result = serialize_graph(
        schema,
        graph,
        sprite_catalog=catalog,
        atlas_cache=cache,
        atlas_known_pages=known,
    )
    return result, time.perf_counter() - started


def main() -> None:
    sprites = {
        f"image-{index}": StaticSprite(_image(index))
        for index in range(UNIQUE_IMAGE_COUNT + 1)
    }
    catalog = SpriteCatalog(sprites)
    nodes = tuple(
        Node(
            f"node-{index}",
            "item",
            f"Node {index}",
            sprites={"thumbnail": SpriteRef(f"image-{index % UNIQUE_IMAGE_COUNT}")},
        )
        for index in range(NODE_COUNT)
    )
    policy = AtlasPolicy(max_tenant_pages=128)
    cache = AtlasCache(policy)
    initial, initial_seconds = _serialize(
        GraphData(nodes, ()), catalog, cache, frozenset()
    )
    initial_pages = initial.envelope["atlas"]["pages"]
    page_ids = frozenset(page["pageId"] for page in initial_pages)
    repeated, repeated_seconds = _serialize(
        GraphData(nodes, ()), catalog, cache, page_ids
    )
    changed_nodes = (
        *nodes,
        Node(
            "node-new",
            "item",
            "New node",
            sprites={"thumbnail": SpriteRef(f"image-{UNIQUE_IMAGE_COUNT}")},
        ),
    )
    changed, changed_seconds = _serialize(
        GraphData(changed_nodes, ()), catalog, cache, page_ids
    )
    locations = {
        layer["sprite"]["pageId"]
        for node in initial.envelope["presentation"]["nodes"]
        for layer in node["badges"]
    }
    tile_area = UNIQUE_IMAGE_COUNT * 72 * 72
    page_area = sum(page["width"] * page["height"] for page in initial_pages)
    evidence = {
        "nodes": NODE_COUNT,
        "uniqueSourceImages": UNIQUE_IMAGE_COUNT,
        "deduplicatedTiles": UNIQUE_IMAGE_COUNT,
        "atlasPages": len(initial_pages),
        "referencedPages": len(locations),
        "fillRatio": round(tile_area / page_area, 4),
        "initialEncodedPageBytes": sum(
            len(page["base64"]) * 3 // 4 for page in initial_pages
        ),
        "unchangedRerunDeltaPages": len(repeated.envelope["atlas"]["pages"]),
        "oneNewImageDeltaPages": len(changed.envelope["atlas"]["pages"]),
        "browserDecodedBytesEstimate": page_area * 4,
        "blobUrlCount": len(initial_pages),
        "oneTileBlobUrlBaseline": UNIQUE_IMAGE_COUNT,
        "initialSerializationSeconds": round(initial_seconds, 6),
        "unchangedSerializationSeconds": round(repeated_seconds, 6),
        "oneNewImageSerializationSeconds": round(changed_seconds, 6),
    }
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
