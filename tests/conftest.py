from pathlib import Path

import pytest
import yaml

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def example_data():
    """Raw YAML of an example, to modify in a test."""
    def load(name):
        return yaml.safe_load((EXAMPLES / f"{name}.yaml").read_text(encoding="utf-8"))
    return load
