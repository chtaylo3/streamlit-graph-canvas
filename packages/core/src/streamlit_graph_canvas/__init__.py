"""Public API for the Streamlit Graph Canvas core distribution."""

from importlib.metadata import version as distribution_version

from .adapters import from_networkx
from .atlas import (
    AtlasCache,
    AtlasPageCache,
    AtlasPolicy,
    atlas_cache,
    atlas_cache_snapshot,
    reset_atlas_caches,
)
from .component import CanvasResult, graph_canvas
from .context import add_sibling_context
from .csp import format_csp, required_csp_directives, streamlit_host_csp
from .errors import Diagnostic, GraphCanvasError, ValidationError
from .images import PngImage, SpriteCatalog, StaticSprite
from .model import (
    ANY_NODE_TYPE,
    AnyNodeType,
    BadgeBinding,
    ChildGroup,
    Edge,
    EdgeStyle,
    EdgeType,
    FitView,
    GraphData,
    GraphSchema,
    GroupDirection,
    GroupDisplay,
    LabelPolicy,
    Node,
    NodeStyle,
    NodeType,
    PaletteTone,
    PortSide,
    PortSpec,
    Region,
    SelectionMode,
    Transport,
)
from .primitives import (
    BadgeContext,
    CirclePrim,
    Prim,
    RectPrim,
    TextPrim,
    validate_primitives,
)
from .protocol import ActionModifiers, CanvasAction, CanvasViewport
from .renderers import (
    RENDERER_API,
    BadgeRenderer,
    EnabledRenderer,
    RendererKind,
    RendererManifest,
    RendererRegistry,
    discover_renderer_diagnostics,
    discover_renderer_manifests,
    enable_renderers,
    parse_renderer_manifest,
)
from .search import SearchCriterion, SearchField, SearchRequest
from .serialization import SerializedGraph, serialize_graph
from .sprites import SpriteBinding, SpriteRef
from .validation import validate
from .warming import WarmingResult, warm_atlas

__all__ = [
    "ANY_NODE_TYPE",
    "RENDERER_API",
    "ActionModifiers",
    "AnyNodeType",
    "AtlasCache",
    "AtlasPageCache",
    "AtlasPolicy",
    "BadgeBinding",
    "BadgeContext",
    "BadgeRenderer",
    "CanvasAction",
    "CanvasResult",
    "CanvasViewport",
    "ChildGroup",
    "CirclePrim",
    "Diagnostic",
    "Edge",
    "EdgeStyle",
    "EdgeType",
    "EnabledRenderer",
    "FitView",
    "GraphCanvasError",
    "GraphData",
    "GraphSchema",
    "GroupDirection",
    "GroupDisplay",
    "LabelPolicy",
    "Node",
    "NodeStyle",
    "NodeType",
    "PaletteTone",
    "PngImage",
    "PortSide",
    "PortSpec",
    "Prim",
    "RectPrim",
    "Region",
    "RendererKind",
    "RendererManifest",
    "RendererRegistry",
    "SearchCriterion",
    "SearchField",
    "SearchRequest",
    "SelectionMode",
    "SerializedGraph",
    "SpriteBinding",
    "SpriteCatalog",
    "SpriteRef",
    "StaticSprite",
    "TextPrim",
    "Transport",
    "ValidationError",
    "WarmingResult",
    "add_sibling_context",
    "atlas_cache",
    "atlas_cache_snapshot",
    "discover_renderer_diagnostics",
    "discover_renderer_manifests",
    "enable_renderers",
    "format_csp",
    "from_networkx",
    "graph_canvas",
    "parse_renderer_manifest",
    "required_csp_directives",
    "reset_atlas_caches",
    "serialize_graph",
    "streamlit_host_csp",
    "validate",
    "validate_primitives",
    "warm_atlas",
]

__version__ = distribution_version("streamlit-graph-canvas")
