import pytest
from streamlit_graph_canvas import (
    BadgeBinding,
    ChildGroup,
    Edge,
    EdgeStyle,
    EdgeType,
    GraphData,
    GraphSchema,
    Node,
    NodeStyle,
    NodeType,
    PaletteTone,
    PortSide,
    PortSpec,
    Region,
    SpriteBinding,
    SpriteRef,
    ValidationError,
    enable_renderers,
    validate,
)


def schema() -> GraphSchema:
    return GraphSchema(
        node_types={
            "service": NodeType("service", ports=(PortSpec("out", PortSide.BOTTOM),)),
            "database": NodeType("database", ports=(PortSpec("in", PortSide.TOP),)),
        },
        edge_types={
            "calls": EdgeType("calls", frozenset({"service"}), frozenset({"database"}))
        },
    )


def test_directed_multigraph_and_self_loop_identities_are_explicit() -> None:
    graph = GraphData(
        nodes=(Node("api", "service", "API"), Node("db", "database", "DB")),
        edges=(
            Edge("primary", "api", "db", "calls", "out", "in"),
            Edge("retry", "api", "db", "calls", "out", "in"),
        ),
    )
    validate(schema(), graph)


def test_missing_endpoint_has_stable_diagnostic() -> None:
    graph = GraphData(
        nodes=(Node("api", "service", "API"),),
        edges=(Edge("bad", "api", "missing", "calls"),),
    )
    with pytest.raises(ValidationError) as error:
        validate(schema(), graph)
    assert error.value.diagnostic.code == "SGC_GRAPH_EDGE_ENDPOINT"


def test_combined_element_budget_is_strict() -> None:
    graph = GraphData(
        nodes=(Node("api", "service", "API"), Node("db", "database", "DB")),
        edges=(Edge("primary", "api", "db", "calls"),),
    )
    with pytest.raises(ValidationError) as error:
        validate(schema(), graph, max_elements=2)
    assert error.value.diagnostic.code == "SGC_BUDGET_EXCEEDED"


COUNT_CHIP = "streamlit-graph-canvas/contrib/count-chip"


def badge_schema(*, required: bool = False) -> GraphSchema:
    return GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                badges=(
                    BadgeBinding(
                        "count", COUNT_CHIP, Region.at(0, 0, 42, 22), required=required
                    ),
                ),
            )
        },
        edge_types={},
        palette={
            "accent": PaletteTone("#2563eb"),
            "on_accent": PaletteTone("#ffffff"),
        },
    )


def sprite_schema(*, required: bool = False) -> GraphSchema:
    return GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                sprites=(
                    SpriteBinding("icon", Region.at(0, 0, 16, 16), required=required),
                ),
            )
        },
        edge_types={},
    )


def code_of(schema_value: GraphSchema, graph: GraphData, **options: object) -> str:
    with pytest.raises(ValidationError) as error:
        validate(schema_value, graph, **options)  # type: ignore[arg-type]
    return error.value.diagnostic.code


API = Node("api", "service", "API")
DB = Node("db", "database", "DB")


@pytest.mark.parametrize(
    ("graph", "code"),
    [
        (GraphData((API, API), ()), "SGC_GRAPH_DUPLICATE_NODE"),
        (
            GraphData(
                (API, DB),
                (Edge("e", "api", "db", "calls"), Edge("e", "api", "db", "calls")),
            ),
            "SGC_GRAPH_DUPLICATE_EDGE",
        ),
        (GraphData((Node("", "service", "blank"),), ()), "SGC_GRAPH_NODE_ID"),
        (GraphData((Node("x", "unknown", "X"),), ()), "SGC_GRAPH_NODE_TYPE"),
        (
            GraphData((API, DB), (Edge("", "api", "db", "calls"),)),
            "SGC_GRAPH_EDGE_ID",
        ),
        (
            GraphData((API, DB), (Edge("e", "api", "db", "unknown"),)),
            "SGC_GRAPH_EDGE_TYPE",
        ),
        (
            GraphData((API, DB), (Edge("e", "db", "db", "calls"),)),
            "SGC_GRAPH_EDGE_SOURCE_TYPE",
        ),
        (
            GraphData((API, DB), (Edge("e", "api", "api", "calls"),)),
            "SGC_GRAPH_EDGE_TARGET_TYPE",
        ),
        (
            GraphData((API, DB), (Edge("e", "api", "db", "calls", "missing"),)),
            "SGC_GRAPH_EDGE_PORT",
        ),
        (
            GraphData((API, DB), (Edge("e", "api", "db", "calls", "out", "nope"),)),
            "SGC_GRAPH_EDGE_PORT",
        ),
        (
            GraphData((Node("x", "service", "X", width=0),), ()),
            "SGC_GRAPH_NODE_GEOMETRY",
        ),
        (
            GraphData((Node("x", "service", "X", height=float("nan")),), ()),
            "SGC_GRAPH_NODE_GEOMETRY",
        ),
        (
            GraphData((Node("x", "service", "X", width=float("inf")),), ()),
            "SGC_GRAPH_NODE_GEOMETRY",
        ),
        (GraphData((Node("x", "service", "X", opacity=1.5),), ()), "SGC_OPACITY"),
        (GraphData((Node("x", "service", "X", opacity=True),), ()), "SGC_OPACITY"),
        (
            GraphData((API, DB), (Edge("e", "api", "db", "calls", opacity=-0.1),)),
            "SGC_OPACITY",
        ),
        (
            GraphData((Node("x", "service", "X", layout_order=True),), ()),
            "SGC_LAYOUT_ORDER",
        ),
        (
            GraphData((Node("x", "service", "X", layout_order=1.5),), ()),  # type: ignore[arg-type]
            "SGC_LAYOUT_ORDER",
        ),
    ],
)
def test_graph_integrity_codes(graph: GraphData, code: str) -> None:
    assert code_of(schema(), graph) == code


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ({"max_elements": 0}, "SGC_BUDGET_INVALID"),
        ({"max_elements": -1}, "SGC_BUDGET_INVALID"),
        ({"max_data_bytes": 0}, "SGC_DATA_BUDGET_INVALID"),
    ],
)
def test_invalid_budgets_fail_closed(options: dict[str, int], code: str) -> None:
    assert code_of(schema(), GraphData((), ()), **options) == code


def test_badge_bindings_require_a_registry_and_declared_names() -> None:
    graph = GraphData((Node("a", "item", "A", badges={"count": 1}),), ())
    assert code_of(badge_schema(), graph) == "SGC_RENDERER_NOT_ENABLED"
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    validate(badge_schema(), graph, renderer_registry=registry)
    extra = GraphData((Node("a", "item", "A", badges={"other": 1}),), ())
    assert (
        code_of(badge_schema(), extra, renderer_registry=registry)
        == "SGC_GRAPH_BADGE_BINDING"
    )
    empty = GraphData((Node("a", "item", "A"),), ())
    validate(badge_schema(), empty, renderer_registry=registry)
    assert (
        code_of(badge_schema(required=True), empty, renderer_registry=registry)
        == "SGC_GRAPH_BADGE_REQUIRED"
    )


def test_sprite_bindings_require_declared_names_and_sprite_refs() -> None:
    undeclared = GraphData(
        (Node("a", "item", "A", sprites={"other": SpriteRef("x")}),), ()
    )
    assert code_of(sprite_schema(), undeclared) == "SGC_GRAPH_SPRITE_BINDING"
    missing = GraphData((Node("a", "item", "A"),), ())
    validate(sprite_schema(), missing)
    assert code_of(sprite_schema(required=True), missing) == "SGC_GRAPH_SPRITE_REQUIRED"
    raw = GraphData((Node("a", "item", "A", sprites={"icon": "x"}),), ())  # type: ignore[dict-item]
    assert code_of(sprite_schema(), raw) == "SGC_GRAPH_SPRITE_REFERENCE"


def node_schema(**node_type: object) -> GraphSchema:
    return GraphSchema(
        node_types={"item": NodeType("item", **node_type)},  # type: ignore[arg-type]
        edge_types={"link": EdgeType("link")},
    )


def edge_schema(edge_type: EdgeType, key: str = "link") -> GraphSchema:
    return GraphSchema(
        node_types={"item": NodeType("item")}, edge_types={key: edge_type}
    )


@pytest.mark.parametrize(
    ("schema_value", "code"),
    [
        (GraphSchema({"other": NodeType("item")}, {}), "SGC_SCHEMA_NODE_TYPE_NAME"),
        (GraphSchema({"": NodeType("")}, {}), "SGC_SCHEMA_NODE_TYPE_NAME"),
        (edge_schema(EdgeType("link"), key="other"), "SGC_SCHEMA_EDGE_TYPE_NAME"),
        (
            node_schema(
                ports=(PortSpec("p", PortSide.TOP), PortSpec("p", PortSide.LEFT))
            ),
            "SGC_SCHEMA_DUPLICATE_PORT",
        ),
        (
            node_schema(
                badges=(
                    BadgeBinding("b", COUNT_CHIP, Region.at(0, 0, 1, 1)),
                    BadgeBinding("b", COUNT_CHIP, Region.at(0, 0, 1, 1)),
                )
            ),
            "SGC_SCHEMA_DUPLICATE_BINDING",
        ),
        (
            node_schema(badges=(BadgeBinding("b", COUNT_CHIP, Region(0, 0, 0, 4)),)),
            "SGC_SCHEMA_BADGE_REGION",
        ),
        (
            node_schema(
                badges=(BadgeBinding("b", COUNT_CHIP, Region(float("nan"), 0, 4, 4)),)
            ),
            "SGC_SCHEMA_BADGE_REGION",
        ),
        (
            node_schema(
                sprites=(
                    SpriteBinding("s", Region.at(0, 0, 1, 1)),
                    SpriteBinding("s", Region.at(0, 0, 1, 1)),
                )
            ),
            "SGC_SCHEMA_DUPLICATE_SPRITE_BINDING",
        ),
        (
            node_schema(sprites=(SpriteBinding("s", Region(0, 0, 4, -1)),)),
            "SGC_SCHEMA_SPRITE_REGION",
        ),
        (
            edge_schema(EdgeType("link", style=EdgeStyle(width=0))),
            "SGC_SCHEMA_EDGE_GEOMETRY",
        ),
        (
            edge_schema(EdgeType("link", style=EdgeStyle(width=float("inf")))),
            "SGC_SCHEMA_EDGE_GEOMETRY",
        ),
        (
            edge_schema(EdgeType("link", style=EdgeStyle(arrow="sideways"))),  # type: ignore[arg-type]
            "SGC_SCHEMA_EDGE_ARROW",
        ),
        (
            edge_schema(EdgeType("link", style=EdgeStyle(stroke="nope"))),
            "SGC_SCHEMA_STYLE_TONE",
        ),
        (node_schema(style=NodeStyle(fill="nope")), "SGC_SCHEMA_STYLE_TONE"),
        (
            edge_schema(EdgeType("link", source_types=frozenset({"ghost"}))),
            "SGC_SCHEMA_EDGE_ENDPOINT_TYPE",
        ),
        (
            edge_schema(EdgeType("link", target_types=frozenset({"ghost"}))),
            "SGC_SCHEMA_EDGE_ENDPOINT_TYPE",
        ),
    ],
)
def test_schema_integrity_codes(schema_value: GraphSchema, code: str) -> None:
    assert code_of(schema_value, GraphData((), ())) == code


def test_badge_and_sprite_bindings_cannot_share_a_name() -> None:
    registry = enable_renderers(["streamlit-graph-canvas-contrib"])
    conflicted = GraphSchema(
        node_types={
            "item": NodeType(
                "item",
                badges=(BadgeBinding("icon", COUNT_CHIP, Region.at(0, 0, 4, 4)),),
                sprites=(SpriteBinding("icon", Region.at(0, 0, 4, 4)),),
            )
        },
        edge_types={},
        palette={"accent": PaletteTone("#000"), "on_accent": PaletteTone("#fff")},
    )
    assert (
        code_of(conflicted, GraphData((), ()), renderer_registry=registry)
        == "SGC_SCHEMA_LAYER_NAME_CONFLICT"
    )


def palette_schema(
    name: str = "brand", light: object = "#123456", dark: object = None
) -> GraphSchema:
    return GraphSchema(
        node_types={},
        edge_types={},
        palette={name: PaletteTone(light, dark)},  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "color",
    [
        "#123",
        "#12345678",
        "rebeccapurple",
        "rgb(1, 2, 3)",
        "oklch(70% 0.1 200 / 50%)",
        "var(--st-primary-color)",
    ],
)
def test_supported_palette_colors_are_accepted(color: str) -> None:
    validate(palette_schema(light=color, dark=color), GraphData((), ()))


@pytest.mark.parametrize(
    ("color", "code"),
    [
        (" #123", "SGC_SCHEMA_PALETTE_COLOR"),
        ("#123 ", "SGC_SCHEMA_PALETTE_COLOR"),
        ("#" + "1" * 128, "SGC_SCHEMA_PALETTE_COLOR"),
        ("#12", "SGC_SCHEMA_PALETTE_COLOR"),
        ("red;background:blue", "SGC_SCHEMA_PALETTE_COLOR"),
        ("red}body{display:none", "SGC_SCHEMA_PALETTE_COLOR"),
        ("expression(alert(1))", "SGC_SCHEMA_PALETTE_COLOR"),
        ("var(--app-secret)", "SGC_SCHEMA_PALETTE_COLOR"),
        ("rgb(1,2,3)/*x*/", "SGC_SCHEMA_PALETTE_COLOR"),
        ("var(--st-x), url(x)", "SGC_SCHEMA_PALETTE_REFERENCE"),
        ("IMAGE-SET(x)", "SGC_SCHEMA_PALETTE_REFERENCE"),
        ("attr(data-x)", "SGC_SCHEMA_PALETTE_REFERENCE"),
        (7, "SGC_SCHEMA_PALETTE_COLOR"),
        (b"#fff", "SGC_SCHEMA_PALETTE_COLOR"),
    ],
)
def test_palette_css_injection_is_rejected(color: object, code: str) -> None:
    assert code_of(palette_schema(light=color), GraphData((), ())) == code
    assert code_of(palette_schema(dark=color), GraphData((), ())) == code


@pytest.mark.parametrize("name", ["", "Brand", "1tone", "tone name", "tone;x"])
def test_palette_tone_names_are_css_safe(name: str) -> None:
    code = code_of(palette_schema(name=name), GraphData((), ()))
    assert code == "SGC_SCHEMA_PALETTE_NAME"


def test_duplicate_child_groups_are_rejected_by_model_and_validator() -> None:
    with pytest.raises(ValueError, match="more than once"):
        NodeType("item", child_groups=(ChildGroup("link"), ChildGroup("link")))
    # Defense in depth: a bypassed frozen declaration still fails validation.
    node_type = NodeType("item", child_groups=(ChildGroup("link"),))
    object.__setattr__(
        node_type, "child_groups", (ChildGroup("link"), ChildGroup("link"))
    )
    bypassed = GraphSchema({"item": node_type}, {"link": EdgeType("link")})
    assert code_of(bypassed, GraphData((), ())) == "SGC_SCHEMA_DUPLICATE_CHILD_GROUP"
