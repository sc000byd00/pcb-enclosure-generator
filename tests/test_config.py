import pytest

from enclosure import ConfigError, params_from_dict


def test_examples_load(example_data):
    for name in "sml":
        p = params_from_dict(example_data(name))
        assert p.name == name and p.parts


def test_defaults_fill_in(example_data):
    p = params_from_dict(example_data("m"))
    assert (p.wall, p.fit, p.screw) == (2.0, 0.25, "M2.5")


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(colour="red"), "unknown top-level key"),
    (lambda d: d["board"].pop("holes"), "board: missing 'holes'"),
    (lambda d: d["board"]["holes"].append([80, 10]), "outside the board"),
    (lambda d: d["board"].update(screw="M4"), "board.screw"),
    (lambda d: d["components"].append({"type": "hdmi", "side": "left", "pos": 10}),
     "unknown type 'hdmi'"),
    (lambda d: d["components"].append({"type": "usb-c", "side": "top", "pos": 10}),
     "side must be one of"),
    (lambda d: d["components"].append({"type": "usb-c", "side": "left"}), "missing 'pos'"),
    (lambda d: d["components"][0].update(colour="red"), "unknown key(s) colour"),
    (lambda d: d["components"][-1].pop("dir"), "flexure button needs dir"),
    (lambda d: d.update(snap_hooks={}), "snap_hooks"),
    (lambda d: d["snap_hooks"].update(front=[90]), "outside the board edge"),
    (lambda d: d.update(shell={"wall": "thick"}), "shell.wall: expected a number"),
])
def test_bad_input_is_reported(example_data, change, message):
    d = example_data("m")
    change(d)
    with pytest.raises(ConfigError, match=None) as e:
        params_from_dict(d)
    assert message in str(e.value)
