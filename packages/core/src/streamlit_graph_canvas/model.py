"""Domain-neutral immutable graph and schema models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .sprites import SpriteBinding, SpriteRef

BUILTIN_PALETTE = {
    "surface": {"light": "var(--st-secondary-background-color)", "dark": None},
    "border": {"light": "var(--st-border-color)", "dark": None},
    "text": {"light": "var(--st-text-color)", "dark": None},
    "muted": {"light": "var(--st-gray-color)", "dark": None},
}


def _mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


class PortSide(StrEnum):
    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


class SelectionMode(StrEnum):
    NONE = "none"
    SINGLE = "single"
    MULTIPLE = "multiple"


class FitView(StrEnum):
    NEVER = "never"
    INITIAL = "initial"
    TOPOLOGY_CHANGE = "topology-change"


class Transport(StrEnum):
    PRIMS = "prims"
    JAVASCRIPT = "javascript"
    RASTER = "raster"
    # Compatibility name/value retained for the 0.1 release-candidate series.
    ATLAS = "atlas"


@dataclass(frozen=True, slots=True)
class PaletteTone:
    light: str
    dark: str | None = None


@dataclass(frozen=True, slots=True)
class NodeStyle:
    width: float = 180
    height: float = 92
    fill: str = "surface"
    stroke: str = "border"
    text: str = "text"
    radius: float = 12


@dataclass(frozen=True, slots=True)
class EdgeStyle:
    stroke: str = "muted"
    width: float = 1.5
    dashed: bool = False
    arrow: Literal["none", "source", "target", "both"] = "none"


@dataclass(frozen=True, slots=True)
class PortSpec:
    name: str
    side: PortSide
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Region:
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def at(cls, x: float, y: float, width: float, height: float) -> Region:
        return cls(x, y, width, height)


@dataclass(frozen=True, slots=True)
class BadgeBinding:
    name: str
    kind: str
    region: Region
    transport: Transport = Transport.PRIMS
    layer: Literal["under", "over"] = "over"
    z: int = 0
    required: bool = False
    options: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", _mapping(self.options))


class GroupDisplay(StrEnum):
    """Presentation policy, evaluated independently for each relationship."""

    TREE = "tree"
    COLLECTION = "collection"
    CUTOFF = "cutoff"


class GroupDirection(StrEnum):
    """Flow direction used inside an expanded child group."""

    RIGHT = "right"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class ChildGroup:
    """Collapse a node's children of one edge type behind an expandable group.

    A node with a large fan-out flattens into one very wide band, because every
    child sits at the same depth. Declaring a group moves those children behind a
    marker on the parent: collapsed they leave the layout entirely, and expanded
    they are laid out inside their own container with their own flow direction,
    so a wide band becomes a compact nested tree.

    Grouping keys on ``edge_type`` because that is the distinction the graph
    already carries. A manifest that both depends on and resolves packages
    declares one group per relationship rather than a parallel vocabulary.
    """

    edge_type: str
    label: str = ""
    threshold: int = 1
    direction: GroupDirection = GroupDirection.RIGHT
    collapsed: bool = True
    display: GroupDisplay = GroupDisplay.CUTOFF

    def __post_init__(self) -> None:
        if not isinstance(self.edge_type, str) or not self.edge_type:
            raise ValueError("ChildGroup.edge_type must be a non-empty string")
        if type(self.threshold) is not int or self.threshold < 1:
            raise ValueError("ChildGroup.threshold must be a positive integer")
        if not isinstance(self.display, GroupDisplay):
            raise ValueError("ChildGroup.display must be a GroupDisplay")
        if not isinstance(self.collapsed, bool):
            raise ValueError("ChildGroup.collapsed must be a bool")
        if not isinstance(self.direction, GroupDirection):
            raise ValueError("ChildGroup.direction must be a GroupDirection")

    @property
    def title(self) -> str:
        """Return the label shown on the group, defaulting to the edge type."""

        return self.label or self.edge_type


@dataclass(frozen=True, slots=True)
class LabelPolicy:
    """Fixed-box label formatting. A type override replaces the entire policy."""

    layout: Literal["path", "wrap", "single"] = "path"
    lines: int = 2
    ellipsis: Literal["auto", "end", "middle"] = "auto"
    font_size: int = 14
    min_font_size: int | None = None
    reveal_mode: Literal["delayed_hover", "controls"] = "delayed_hover"
    reveal_delay_ms: int = 600
    reveal_hover: bool = True
    reveal_focus: bool | None = None
    reveal_button: bool | None = None

    def __post_init__(self) -> None:
        if self.layout not in ("path", "wrap", "single"):
            raise ValueError(
                "LabelPolicy.layout must be path, wrap, or single; "
                "box growth is unsupported"
            )
        if type(self.lines) is not int or not 1 <= self.lines <= 6:
            raise ValueError("LabelPolicy.lines must be an integer from 1 to 6")
        if self.layout == "single" and self.lines != 1:
            raise ValueError("LabelPolicy single layout requires lines=1")
        if self.layout == "path" and self.lines != 2:
            raise ValueError("LabelPolicy path layout requires lines=2")
        if self.ellipsis not in ("auto", "end", "middle"):
            raise ValueError("LabelPolicy.ellipsis must be auto, end, or middle")
        if self.layout == "wrap" and self.ellipsis == "middle":
            raise ValueError(
                "LabelPolicy wrap layout is incompatible with middle ellipsis"
            )
        if type(self.font_size) is not int or self.font_size < 1:
            raise ValueError("LabelPolicy.font_size must be a positive integer")
        if self.min_font_size is not None and (
            type(self.min_font_size) is not int
            or not 1 <= self.min_font_size <= self.font_size
        ):
            raise ValueError(
                "LabelPolicy.min_font_size must be between 1 and font_size"
            )
        if self.reveal_mode not in ("delayed_hover", "controls"):
            raise ValueError(
                "LabelPolicy.reveal_mode must be delayed_hover or controls"
            )
        if (
            type(self.reveal_delay_ms) is not int
            or not 0 <= self.reveal_delay_ms <= 2_147_483_647
        ):
            raise ValueError(
                "LabelPolicy.reveal_delay_ms must be an integer from 0 to 2147483647"
            )
        for name in ("reveal_focus", "reveal_button"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise ValueError(f"LabelPolicy.{name} must be boolean or None")
            if self.reveal_mode == "delayed_hover" and value is True:
                raise ValueError(
                    f"LabelPolicy.{name}=True requires reveal_mode='controls'"
                )
        for name in ("reveal_hover",):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"LabelPolicy.{name} must be boolean")


@dataclass(frozen=True, slots=True)
class NodeType:
    name: str
    style: NodeStyle = NodeStyle()
    ports: tuple[PortSpec, ...] = ()
    badges: tuple[BadgeBinding, ...] = ()
    sprites: tuple[SpriteBinding, ...] = ()
    child_groups: tuple[ChildGroup, ...] = ()
    label_policy: LabelPolicy | None = None

    def __post_init__(self) -> None:
        if self.label_policy is not None and not isinstance(
            self.label_policy, LabelPolicy
        ):
            raise ValueError("NodeType.label_policy must be a LabelPolicy or None")
        seen: set[str] = set()
        for group in self.child_groups:
            if not isinstance(group, ChildGroup):
                raise ValueError("child_groups entries must be ChildGroup instances")
            if group.edge_type in seen:
                raise ValueError(
                    f"node type {self.name!r} groups edge type "
                    f"{group.edge_type!r} more than once"
                )
            seen.add(group.edge_type)


@dataclass(frozen=True, slots=True)
class AnyNodeType:
    """Sentinel allowing an edge type to connect to every node type."""


ANY_NODE_TYPE = AnyNodeType()
EndpointTypes = frozenset[str] | AnyNodeType


@dataclass(frozen=True, slots=True)
class EdgeType:
    name: str
    source_types: EndpointTypes = ANY_NODE_TYPE
    target_types: EndpointTypes = ANY_NODE_TYPE
    style: EdgeStyle = EdgeStyle()


@dataclass(frozen=True, slots=True)
class GraphSchema:
    node_types: Mapping[str, NodeType]
    edge_types: Mapping[str, EdgeType]
    palette: Mapping[str, PaletteTone] = field(default_factory=dict)
    label_policy: LabelPolicy = LabelPolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.label_policy, LabelPolicy):
            raise ValueError("GraphSchema.label_policy must be a LabelPolicy")
        object.__setattr__(self, "node_types", _mapping(self.node_types))
        object.__setattr__(self, "edge_types", _mapping(self.edge_types))
        object.__setattr__(self, "palette", _mapping(self.palette))


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    type: str
    label: str
    data: Mapping[str, Any] = field(default_factory=dict)
    badges: Mapping[str, Any] = field(default_factory=dict)
    width: float | None = None
    height: float | None = None
    disabled: bool = False
    dimmed: bool = False
    sprites: Mapping[str, SpriteRef] = field(default_factory=dict)
    opacity: float | None = None
    layout_order: int | None = None
    display_label: str | None = None

    def __post_init__(self) -> None:
        if self.display_label is not None and not isinstance(self.display_label, str):
            raise ValueError("Node.display_label must be a string or None")
        object.__setattr__(self, "data", _mapping(self.data))
        object.__setattr__(self, "badges", _mapping(self.badges))
        object.__setattr__(self, "sprites", _mapping(self.sprites))


@dataclass(frozen=True, slots=True)
class Edge:
    id: str
    source: str
    target: str
    type: str
    source_port: str | None = None
    target_port: str | None = None
    label: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    dimmed: bool = False
    emphasized: bool = False
    optional: bool = False
    opacity: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _mapping(self.data))


@dataclass(frozen=True, slots=True)
class GraphData:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]

    @classmethod
    def of(cls, *, nodes: list[Node], edges: list[Edge]) -> GraphData:
        return cls(tuple(nodes), tuple(edges))
