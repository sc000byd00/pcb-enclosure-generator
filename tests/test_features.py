"""Keep-out zones, support posts, M2 inserts and the low-profile switch."""

import pytest

from enclosure import build, params_from_dict
from enclosure import kicad
from enclosure.checks import run
from enclosure.config import ConfigError


def built(data):
    p = params_from_dict(data)
    enc, parts, pcb, bodies, env = build(p)
    res = run(enc, parts, pcb, bodies, env, overhang=False)
    return enc, parts, pcb, {c.id.split(":")[0]: c for c in res}


def failures(checks):
    return {k for k, c in checks.items() if c.ok is False}


def test_keepout_past_the_edge_widens_one_side(example_data):
    plain, *_ = built(example_data("m"))
    d = example_data("m")
    d["components"].append({"type": "keepout", "x": 70, "y": 10, "w": 15, "d": 30})
    enc, parts, pcb, checks = built(d)
    assert failures(checks) == set()
    assert checks["keepout-1"].ok
    assert enc.gap["right"] == pytest.approx(15 + enc.p.fit + enc.p.lip_w + 0.1)
    assert enc.gap["left"] == plain.gap["left"]
    assert enc.out_x == pytest.approx(plain.out_x + enc.gap["right"] - plain.gap["right"])
    # the board solid follows the offset: its front left corner sits at (ox, oy)
    bb = pcb.bounding_box()
    assert (bb.min.X, bb.min.Y) == (pytest.approx(enc.ox), pytest.approx(enc.oy))


def test_keepout_over_a_boss_fails(example_data):
    d = example_data("m")
    d["components"].append({"type": "keepout", "x": 4, "y": 1, "w": 8, "d": 6})  # hole at (8, 4)
    _, _, _, checks = built(d)
    assert "keepout-1" in failures(checks)


def test_keepout_must_touch_the_board(example_data):
    d = example_data("m")
    d["components"].append({"type": "keepout", "x": 75, "y": 10, "w": 5, "d": 5})
    with pytest.raises(ConfigError, match="keepout"):
        params_from_dict(d)


def test_support_post_holds_the_board_without_failing_the_wall_check(example_data):
    d = example_data("m")
    _, plain_parts, _, _ = built(example_data("m"))
    d["components"].append({"type": "post", "x": 35, "y": 30, "dia": 4})
    enc, parts, pcb, checks = built(d)
    assert failures(checks) == set()
    assert parts["base"].volume > plain_parts["base"].volume + 50  # Ø4 x 5 mm = 63 mm3
    assert pcb.distance_to(parts["base"]) == pytest.approx(0, abs=1e-3)  # board rests on it


def test_m2_inserts(example_data):
    d = example_data("m")
    d["board"]["screw"] = "M2"
    enc, _, _, checks = built(d)
    assert failures(checks) == set()
    assert enc.ins["hole"] == 3.2


def test_low_profile_switch_lengthens_the_plunger(example_data):
    _, plain_parts, _, _ = built(example_data("m"))
    d = example_data("m")
    btn = next(c for c in d["components"] if c["type"] == "button")
    btn["switch"] = "ts-1187a"
    enc, parts, pcb, checks = built(d)
    assert failures(checks) == set()
    assert enc.flex_sw["h"] == 1.5
    # plunger (r 2) reaches 3.5 mm further down: 5.0 mm switch -> 1.5 mm switch
    extra = parts["lid"].volume - plain_parts["lid"].volume
    assert extra == pytest.approx(3.14159 * 2.0 ** 2 * 3.5, rel=0.02)


def test_unknown_switch_is_reported(example_data):
    d = example_data("m")
    next(c for c in d["components"] if c["type"] == "button")["switch"] = "12x12"
    with pytest.raises(ConfigError, match="switch"):
        params_from_dict(d)


def test_kicad_names_for_switch_and_m2():
    assert kicad._classify("SW_Push_1P1T_XKB_TS-1187A") == "button"
    assert next(s for limit, s in kicad.SCREWS if 2.2 <= limit) == "M2"
    assert next(s for limit, s in kicad.SCREWS if 2.7 <= limit) == "M2.5"
