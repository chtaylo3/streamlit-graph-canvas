"""Stock count-chip badge renderer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from streamlit_graph_canvas import BadgeContext, Prim, RectPrim, TextPrim


@dataclass(frozen=True, slots=True)
class CountChipRenderer:
    kind: str = "streamlit-graph-canvas/contrib/count-chip"
    renderer_api: int = 1

    def render(
        self, data: object, options: Mapping[str, object], context: BadgeContext
    ) -> Sequence[Prim]:
        if not isinstance(data, int) or isinstance(data, bool):
            raise ValueError("count-chip data must be an integer")
        label = str(data)
        if options.get("prefix") is not None:
            label = f"{options['prefix']}{label}"
        return (
            RectPrim(
                0,
                0,
                context.width,
                context.height,
                "accent",
                min(context.width, context.height) / 2,
            ),
            TextPrim(
                context.width / 2,
                context.height / 2 + 4,
                label,
                "on_accent",
            ),
        )


renderer = CountChipRenderer()
