"""Bad designs must fail the right check."""

import pytest

from enclosure import build, params_from_dict
from enclosure.checks import run


def failed_ids(data):
    p = params_from_dict(data)
    res = run(*build(p), overhang=False)
    return {c.id.split(":")[0] for c in res if c.ok is False}


def test_thin_wall_fails(example_data):
    d = example_data("s")
    d["shell"] = {"wall": 1.2}
    assert "walls" in failed_ids(d)


def test_short_hooks_fail_on_strain(example_data):
    d = example_data("s")
    d["hook"] = {"target_strain": 0.03}  # hooks get shorter, strain above 2 %
    assert "hook-strain" in failed_ids(d)


def test_connector_into_boss_collides(example_data):
    d = example_data("m")
    d["components"][0]["pos"] = 5.0  # USB-C right next to the hole at (8, 4)
    assert "collisions" in failed_ids(d)


def test_component_taller_than_design_height_fails(example_data):
    d = example_data("s")
    d["components"].append({"type": "cap", "x": 10, "y": 15, "dia": 5, "h": 9})
    assert {"component-height", "collisions"} <= failed_ids(d)


@pytest.mark.parametrize("name", ["s", "m"])
def test_unchanged_examples_have_no_failures(example_data, name):
    assert failed_ids(example_data(name)) == set()


def test_component_inside_base_bounding_box_is_still_checked(example_data):
    # A module sticking 1 mm past the board edge into the wall, its bounding box fully
    # inside the base's. Regression for BoundBox.overlaps(), which ignores contained boxes.
    d = example_data("m")
    d["components"].append({"type": "module", "x": 66, "y": 30, "w": 5, "d": 5, "h": 2})
    assert "collisions" in failed_ids(d)
