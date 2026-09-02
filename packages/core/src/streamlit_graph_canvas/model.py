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


@dataclass(frozen=True, slots=True)
class NodeType:
    name: str
    style: NodeStyle = NodeStyle()
    ports: tuple[PortSpec, ...] = ()
    badges: tuple[BadgeBinding, ...] = ()
    sprites: tuple[SpriteBinding, ...] = ()


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

    def __post_init__(self) -> None:
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

    def __post_init__(self) -> None:
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _mapping(self.data))


@dataclass(frozen=True, slots=True)
class GraphData:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]

    @classmethod
    def of(cls, *, nodes: list[Node], edges: list[Edge]) -> GraphData:
        return cls(tuple(nodes), tuple(edges))
