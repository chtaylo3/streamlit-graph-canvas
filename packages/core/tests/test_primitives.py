import math

import pytest
from streamlit_graph_canvas import (
    BadgeContext,
    RectPrim,
    TextPrim,
    ValidationError,
    validate_primitives,
)


def context() -> BadgeContext:
    return BadgeContext(40, 20, frozenset({"accent", "on_accent"}))


def test_valid_primitives_become_json_compatible() -> None:
    result = validate_primitives(
        (RectPrim(0, 0, 40, 20, "accent", 10), TextPrim(20, 14, "3", "on_accent")),
        context(),
    )
    assert [item["kind"] for item in result] == ["rect", "text"]


@pytest.mark.parametrize(
    ("primitive", "code"),
    [
        (RectPrim(0, 0, math.inf, 20, "accent"), "SGC_PRIMS_GEOMETRY"),
        (RectPrim(0, 0, 40, 20, "missing"), "SGC_PRIMS_TONE"),
        (TextPrim(0, 0, "x" * 1025, "accent"), "SGC_PRIMS_TEXT_LIMIT"),
        ({"kind": "script", "value": "alert(1)"}, "SGC_PRIMS_TYPE"),
    ],
)
def test_unsafe_primitives_are_rejected(primitive, code: str) -> None:
    with pytest.raises(ValidationError) as error:
        validate_primitives((primitive,), context())
    assert error.value.diagnostic.code == code


def test_primitive_count_is_bounded() -> None:
    with pytest.raises(ValidationError) as error:
        validate_primitives(
            tuple(RectPrim(0, 0, 1, 1, "accent") for _ in range(201)), context()
        )
    assert error.value.diagnostic.code == "SGC_PRIMS_LIMIT"
