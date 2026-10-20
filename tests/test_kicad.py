"""Reading KiCad boards: outline, holes, components, edge connectors, overrides."""

import sys
from pathlib import Path

import pytest

from enclosure import build, params_from_dict
from enclosure.checks import passed, run
from enclosure.kicad import KicadError, apply_overrides, auto_layout, read_board
from enclosure.sexpr import parse

KICAD = Path(__file__).parent.parent / "examples" / "kicad"
sys.path.insert(0, str(KICAD))
import make_boards as mb  # noqa: E402


def by_ref(data):
    return {c["ref"]: c for c in data["components"] if "ref" in c}


def test_sexpr_parses_strings_and_nesting():
    tree = parse('(a (b "x y" 1.5) (c "q\\"uote"))')
    assert tree == ["a", ["b", "x y", "1.5"], ["c", 'q"uote']]


def test_esp32_node_is_read_correctly(tmp_path):
    f = tmp_path / "b.kicad_pcb"
    f.write_text(mb.esp32_node(), encoding="utf-8")
    data, warnings, _ = read_board(f)
    b = data["board"]
    assert b["size"] == [70.0, 50.0]
    assert b["corner_radius"] == pytest.approx(1.5)
    assert b["screw"] == "M2.5"
    assert sorted(map(tuple, b["holes"])) == [(8, 4), (8, 46), (62, 4), (62, 46)]
    c = by_ref(data)
    assert "R1" not in c and "R2" not in c  # small passives are ignored
    assert c["J1"] == {"ref": "J1", "type": "usb-c", "side": "left", "pos": 25.0,
                       "overhang": 0.6}
    assert (c["U1"]["type"], c["U1"]["x"], c["U1"]["y"], c["U1"]["w"], c["U1"]["d"]) == \
        ("module", 36.0, 16.0, 25.5, 18.0)
    assert (c["C1"]["dia"], c["C1"]["h"]) == (6.3, 7.7)
    assert c["J2"]["type"] == "header" and c["J2"]["w"] == pytest.approx(20.32)
    assert (c["SW1"]["x"], c["SW1"]["y"], c["SW1"]["dir"]) == (26.0, 38.0, "+x")
    assert (c["D1"]["x"], c["D1"]["y"]) == (14.0, 38.0)
    assert warnings == []


def test_gateway_connectors_on_back_edge(tmp_path):
    f = tmp_path / "b.kicad_pcb"
    f.write_text(mb.gateway(), encoding="utf-8")
    data, _, _ = read_board(f)
    c = by_ref(data)
    assert data["board"]["screw"] == "M3"
    assert data["board"]["corner_radius"] == 0.0
    assert (c["J1"]["type"], c["J1"]["side"], c["J1"]["pos"], c["J1"]["overhang"]) == \
        ("barrel", "back", 14.0, 0.0)
    assert (c["J2"]["type"], c["J2"]["side"], c["J2"]["overhang"]) == ("terminal", "back", 0.3)


def small_board(*extra):
    items = mb.outline_rect(60.0, 40.0)
    items += [mb.footprint("MountingHole:MountingHole_3.2mm_M3", f"H{i}", "MH", *mb.kc(x, y, 40))
              for i, (x, y) in enumerate([(4, 4), (56, 4), (4, 36), (56, 36)])]
    return mb.board_file("test", items + list(extra))


@pytest.mark.parametrize("rot, at, side, pos", [
    (180, (30, 3.075), "front", 30.0),   # opening turned towards the front edge
    (270, (56.925, 20), "right", 20.0),  # and towards the right edge
])
def test_rotated_connector_finds_its_edge(tmp_path, rot, at, side, pos):
    usb = mb.footprint("Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P", "J1", "USB",
                       *mb.kc(*at, 40), rot)
    f = tmp_path / "b.kicad_pcb"
    f.write_text(small_board(usb), encoding="utf-8")
    c = by_ref(read_board(f)[0])["J1"]
    assert (c["side"], c["pos"], c["overhang"]) == (side, pos, 0.6)


def test_bottom_side_and_unknown_parts_are_reported(tmp_path):
    bottom = mb.footprint("RF_Module:ESP32-WROOM-32", "U9", "x", *mb.kc(30, 20, 40), 0, "B.Cu")
    unknown = mb.footprint("Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering",
                           "U8", "x", *mb.kc(30, 20, 40)).replace(
        "Package_LGA:Bosch_LGA", "Package_LGA:Mystery_LGA")
    f = tmp_path / "b.kicad_pcb"
    f.write_text(small_board(bottom, unknown), encoding="utf-8")
    data, warnings, _ = read_board(f)
    assert "U9" not in by_ref(data)
    assert any("U9" in w and "bottom side" in w for w in warnings)
    assert by_ref(data)["U8"]["h"] == 2.0
    assert any("U8" in w and "unknown height" in w for w in warnings)


def test_overrides_and_layout(tmp_path):
    f = tmp_path / "b.kicad_pcb"
    f.write_text(mb.esp32_node(), encoding="utf-8")
    data, _, _ = read_board(f)
    apply_overrides(data, {"ignore": ["J2"], "parts": {"C1": {"h": 9.0}},
                           "add": [{"type": "vent", "side": "right", "pos": 25, "n": 3,
                                    "w": 1.6, "h": 6, "pitch": 3.4}],
                           "button": "flex"})
    auto_layout(data)
    c = by_ref(data)
    assert "J2" not in c and c["C1"]["h"] == 9.0
    assert data["board"]["component_height"] == 9.0
    assert set(data["snap_hooks"]) == {"front", "back"}
    with pytest.raises(KicadError, match="unknown reference"):
        apply_overrides(data, {"parts": {"X7": {"h": 1}}})


def test_hooks_avoid_connector_openings(tmp_path):
    f = tmp_path / "b.kicad_pcb"
    f.write_text(mb.gateway(), encoding="utf-8")
    data, _, _ = read_board(f)
    auto_layout(data)
    for x in data["snap_hooks"]["back"]:
        assert not 14 - 7.5 - 3.4 < x < 14 + 7.5 + 3.4  # barrel jack window
        assert not 32 - 8.1 - 3.4 < x < 32 + 8.1 + 3.4  # terminal window


def test_not_a_board_file(tmp_path):
    f = tmp_path / "x.kicad_pcb"
    f.write_text('(kicad_sch (version 1))', encoding="utf-8")
    with pytest.raises(KicadError):
        read_board(f)


@pytest.mark.parametrize("name", ["esp32-node", "gateway"])
def test_example_boards_build_and_pass(name):
    import yaml
    data, _, _ = read_board(KICAD / f"{name}.kicad_pcb")
    apply_overrides(data, yaml.safe_load((KICAD / f"{name}.overrides.yaml").read_text()))
    auto_layout(data)
    p = params_from_dict(data)
    res = run(*build(p), overhang=False)
    assert passed(res), [c.message for c in res if c.ok is False]


def test_committed_example_files_are_up_to_date():
    for name, make in mb.BOARDS.items():
        assert (KICAD / f"{name}.kicad_pcb").read_text(encoding="utf-8") == make(), \
            f"run examples/kicad/make_boards.py ({name})"
