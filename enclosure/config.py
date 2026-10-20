"""Enclosure parameters and loading them from YAML.

A board file only needs the board itself, its components and where the snap
hooks go; everything else has a default. See examples/*.yaml.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .specs import CONNECTORS, INSERTS, SIDE_NAMES


class ConfigError(ValueError):
    """Invalid board file. The message names the offending key."""


@dataclass
class Params:
    name: str
    title: str
    pcb: tuple  # board size x, y
    holes: list  # mounting holes, board coordinates
    parts: list  # components and openings
    comp_h: float  # tallest component above the board top
    hooks: dict  # side -> hook positions along that side, board coordinates
    screw: str = "M2.5"
    pcb_t: float = 1.6
    pcb_r: float = 1.5  # board corner radius
    standoff_h: float = 5.0  # board bottom above the floor
    wall: float = 2.0
    floor: float = 2.0
    lid_t: float = 2.0
    corner_r: float = 5.0  # outer radius of the vertical edges
    pcb_gap: float = 0.5  # board to wall
    fit: float = 0.25  # lid lip and hooks to wall
    cut_clear: float = 0.4  # around connectors, per side
    lid_gap: float = 1.5  # tallest component to lid
    lip_w: float = 1.2
    lip_h: float = 2.5
    # snap hooks
    hook_t: float = 1.2
    hook_w: float = 6.0
    hook_d: float = 1.0  # barb depth
    hook_land: float = 0.4
    hook_lead_deg: float = 30.0  # lead-in, against the closing direction
    hook_ret_deg: float = 45.0  # retention face, printable without support
    hook_play: float = 0.1  # vertical play of the barb in its window
    strain_target: float = 0.016  # hooks are made as long as this needs
    # button
    button: str = "flex"  # flex: flexure in the lid, cap: separate cap
    flex_len: float = 12.0
    flex_w: float = 8.0
    flex_t: float = 1.2
    flex_slot: float = 0.8
    btn_gap: float = 0.3
    cap_d: float = 7.0
    cap_fit: float = 0.3
    cap_proud: float = 1.0
    # light pipes
    lp_d: float = 3.0
    lp_fit: float = 0.1
    lp_head_d: float = 5.0
    lp_head_h: float = 1.0
    lp_gap: float = 0.5  # tip above the LED
    sleeve_h: float = 3.0
    # wall mount: keyhole x positions (enclosure coordinates, y = 0)
    keyholes: list = field(default_factory=list)
    # printing and limits
    bed_chamfer: float = 0.6
    parting_chamfer: float = 0.4
    min_wall: float = 1.6
    min_web: float = 1.0
    min_local: float = 0.8  # remaining wall behind a plug recess
    pcb_under: float = 1.5  # free space under the board (solder joints)


# YAML section -> {yaml key: Params field}
SECTIONS = {
    "board": {"size": "pcb", "thickness": "pcb_t", "corner_radius": "pcb_r", "holes": "holes",
              "screw": "screw", "standoff": "standoff_h", "component_height": "comp_h"},
    "shell": {"wall": "wall", "floor": "floor", "lid": "lid_t", "corner_radius": "corner_r"},
    "clearance": {"board": "pcb_gap", "lid_fit": "fit", "cutout": "cut_clear",
                  "lid_gap": "lid_gap"},
    "lid_lip": {"width": "lip_w", "height": "lip_h"},
    "hook": {"thickness": "hook_t", "width": "hook_w", "barb": "hook_d", "land": "hook_land",
             "lead_angle": "hook_lead_deg", "retention_angle": "hook_ret_deg",
             "play": "hook_play", "target_strain": "strain_target"},
    "flexure": {"length": "flex_len", "width": "flex_w", "thickness": "flex_t",
                "slot": "flex_slot", "gap": "btn_gap"},
    "cap": {"diameter": "cap_d", "fit": "cap_fit", "proud": "cap_proud"},
    "light_pipe": {"diameter": "lp_d", "fit": "lp_fit", "head_diameter": "lp_head_d",
                   "head_height": "lp_head_h", "gap": "lp_gap", "sleeve": "sleeve_h"},
    "print": {"bed_chamfer": "bed_chamfer", "parting_chamfer": "parting_chamfer"},
    "limits": {"min_wall": "min_wall", "min_web": "min_web", "min_local": "min_local",
               "under_board": "pcb_under"},
}
TOP_LEVEL = {"name", "title", "components", "snap_hooks", "button", "wall_mount"} | set(SECTIONS)
REQUIRED_BOARD = ("size", "holes", "component_height")

# component type -> required keys, optional keys with defaults
COMPONENTS = {
    **{t: (("side", "pos"), {"overhang": 0.0, "z": 0.0}) for t in CONNECTORS},
    "vent": (("side", "pos", "n", "w", "h", "pitch"), {"z": 1.5}),
    "led": (("x", "y"), {}),
    "button": (("x", "y"), {"dir": None}),
    "module": (("x", "y", "w", "d", "h"), {}),
    "header": (("x", "y", "w", "d", "h"), {}),
    "sensor": (("x", "y", "w", "d", "h"), {}),
    "cap": (("x", "y", "dia", "h"), {}),
}


def _num(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}: expected a number, got {value!r}")
    return float(value)


def _pair(value, where):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{where}: expected [x, y], got {value!r}")
    return (_num(value[0], where), _num(value[1], where))


def _component(raw, i):
    where = f"components[{i}]"
    if not isinstance(raw, dict) or "type" not in raw:
        raise ConfigError(f"{where}: needs a 'type'")
    t = raw["type"]
    if t not in COMPONENTS:
        raise ConfigError(f"{where}: unknown type {t!r} (known: {', '.join(COMPONENTS)})")
    required, optional = COMPONENTS[t]
    unknown = set(raw) - {"type", "ref", *required, *optional}
    if unknown:
        raise ConfigError(f"{where} ({t}): unknown key(s) {', '.join(sorted(unknown))}")
    c = {"type": t}
    if "ref" in raw:  # reference designator, e.g. from KiCad; kept for messages
        c["ref"] = str(raw["ref"])
    for k in required:
        if k not in raw:
            raise ConfigError(f"{where} ({t}): missing {k!r}")
    for k in (*required, *optional):
        v = raw.get(k, optional.get(k))
        if k == "side":
            if v not in SIDE_NAMES:
                raise ConfigError(f"{where}: side must be one of {', '.join(SIDE_NAMES)}")
        elif k == "dir":
            if v is not None and v not in ("+x", "-x"):
                raise ConfigError(f"{where}: dir must be '+x' or '-x'")
        elif k == "n":
            if not isinstance(v, int) or v < 1:
                raise ConfigError(f"{where}: n must be a positive integer")
        elif v is not None:
            v = _num(v, f"{where}.{k}")
        c[k] = v
    return c


def params_from_dict(data, default_name="board"):
    if not isinstance(data, dict):
        raise ConfigError("board file must be a mapping")
    unknown = set(data) - TOP_LEVEL
    if unknown:
        raise ConfigError(f"unknown top-level key(s): {', '.join(sorted(unknown))}")
    board = data.get("board")
    if not isinstance(board, dict):
        raise ConfigError("missing section 'board'")
    for k in REQUIRED_BOARD:
        if k not in board:
            raise ConfigError(f"board: missing {k!r}")

    kw = {}
    for section, mapping in SECTIONS.items():
        values = data.get(section, {}) or {}
        if not isinstance(values, dict):
            raise ConfigError(f"{section}: expected a mapping")
        unknown = set(values) - set(mapping)
        if unknown:
            raise ConfigError(f"{section}: unknown key(s) {', '.join(sorted(unknown))}")
        for key, value in values.items():
            target = mapping[key]
            where = f"{section}.{key}"
            if target == "pcb":
                kw[target] = _pair(value, where)
            elif target == "holes":
                kw[target] = [_pair(h, f"{where}[{i}]") for i, h in enumerate(value)]
            elif target == "screw":
                if value not in INSERTS:
                    raise ConfigError(f"{where}: must be one of {', '.join(INSERTS)}")
                kw[target] = value
            else:
                kw[target] = _num(value, where)

    parts = [_component(c, i) for i, c in enumerate(data.get("components") or [])]
    hooks = data.get("snap_hooks") or {}
    if not isinstance(hooks, dict) or not hooks:
        raise ConfigError("snap_hooks: give at least one side with hook positions")
    for side, xs in hooks.items():
        if side not in SIDE_NAMES:
            raise ConfigError(f"snap_hooks: unknown side {side!r}")
        hooks[side] = [_num(x, f"snap_hooks.{side}") for x in (xs or [])]

    button = data.get("button", "flex")
    if button not in ("flex", "cap"):
        raise ConfigError("button: must be 'flex' or 'cap'")
    keyholes = [_num(x, "wall_mount") for x in (data.get("wall_mount") or [])]

    p = Params(name=str(data.get("name", default_name)), title=str(data.get("title", "")),
               parts=parts, hooks=hooks, button=button, keyholes=keyholes, **kw)
    _validate(p)
    return p


def _validate(p):
    px, py = p.pcb
    if px <= 0 or py <= 0:
        raise ConfigError("board.size: must be positive")
    for i, (hx, hy) in enumerate(p.holes):
        if not (0 < hx < px and 0 < hy < py):
            raise ConfigError(f"board.holes[{i}]: ({hx:g}, {hy:g}) is outside the board")
    length = {"left": py, "right": py, "front": px, "back": px}
    for side, xs in p.hooks.items():
        for x in xs:
            if not 0 <= x <= length[side]:
                raise ConfigError(f"snap_hooks.{side}: {x:g} is outside the board edge")
    for i, c in enumerate(p.parts):
        if "side" in c and not 0 <= c["pos"] <= length[c["side"]]:
            raise ConfigError(f"components[{i}]: pos {c['pos']:g} is outside the {c['side']} edge")
        if "x" in c and not (0 <= c["x"] <= px and 0 <= c["y"] <= py):
            raise ConfigError(f"components[{i}]: ({c['x']:g}, {c['y']:g}) is outside the board")
    buttons = [c for c in p.parts if c["type"] == "button"]
    if p.button == "flex":
        for c in buttons:
            if c["dir"] is None:
                raise ConfigError("button: a flexure button needs dir '+x' or '-x' "
                                  "(direction from the switch to the flexure root)")
    elif len(buttons) != 1:
        raise ConfigError("button: 'cap' supports exactly one button")


def load(path):
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"{path.name}: not valid YAML ({e})") from e
    try:
        return params_from_dict(data, default_name=path.stem)
    except ConfigError as e:
        raise ConfigError(f"{path.name}: {e}") from e
