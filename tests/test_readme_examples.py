import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "readme",
    [ROOT / "packages/core/README.md", ROOT / "packages/contrib/README.md"],
)
def test_package_readme_python_examples_execute(readme: Path) -> None:
    blocks = re.findall(
        r"```python\n(.*?)```", readme.read_text(encoding="utf-8"), re.DOTALL
    )
    assert blocks
    namespace = {"__name__": "__readme_example__"}
    for block in blocks:
        exec(compile(block, str(readme), "exec"), namespace)
