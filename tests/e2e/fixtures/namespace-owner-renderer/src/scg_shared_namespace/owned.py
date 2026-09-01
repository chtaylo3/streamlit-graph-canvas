"""Leaf module owned by a different distribution in a shared namespace."""

from streamlit_graph_canvas import BadgeContext, Prim


class CrossOwnedRenderer:
    kind = "streamlit-graph-canvas/fixture/cross-import"
    renderer_api = 1

    def render(
        self, data: object, options: object, context: BadgeContext
    ) -> tuple[Prim, ...]:
        return ()


renderer = CrossOwnedRenderer()
