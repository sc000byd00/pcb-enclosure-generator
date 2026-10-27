"""Read a KiCad board (.kicad_pcb, KiCad 6 to 8) into a board description.

What is read:
- board outline from Edge.Cuts (rectangle, optionally with rounded corners), thickness
- mounting holes from MountingHole footprints (drill -> M2.5 or M3)
- components on the top side, classified by footprint name (see RULES); position and
  size from the F.Fab outline, else the courtyard, else the pads
- edge connectors: the board edge they stick out of, position along it, overhang

The result is a dict in the same format as a board YAML file, so it can be reviewed,
adjusted with an overrides file and built like any other board.

Board coordinates: origin at the front left corner, x to the right, y to the back. The
front edge is the bottom edge of the board in KiCad (largest y).
"""

import math
import re
from pathlib import Path

from .sexpr import child, children, floats, parse, value
from .specs import CONNECTORS, SWITCHES

# footprint name (without library) -> component type
RULES = [
    (r"^MountingHole", "hole"),
    (r"USB_C_Receptacle", "usb-c"),
    (r"^BarrelJack", "barrel"),
    (r"^TerminalBlock", "terminal"),
    (r"^LED_(0402|0603|0805|1206)|^LED_SMD", "led"),
    (r"^SW_PUSH_6mm|^SW_Push_1P1T_NO_6x6|^SW_SPST_TL3342|^SW_Push_1P1T_XKB_TS-1187A", "button"),
    (r"^ESP32-|^ESP8266|^RF_Module|^nRF52.*Module|^RP2040.*Module", "module"),
    (r"^PinHeader_|^PinSocket_", "header"),
    (r"^CP_Elec_|^C_Elec_", "cap"),
    (r"^(R|C|L|D|LED)_(01005|0201|0402|0603|0805|1206)", "ignore"),
]

# known heights above the board (mm), first match wins
HEIGHTS = [
    (r"^ESP32-C3-MINI|^ESP32-S3-MINI|^ESP32-MINI", 2.55),
    (r"^ESP32-WRO", 3.1),
    (r"^PinHeader_.*Horizontal|^PinSocket_.*Horizontal", 2.5),
    (r"^PinHeader_|^PinSocket_", 8.5),
    (r"^Bosch_LGA", 0.93),
    (r"^ESP32-C3-WROOM-02", 3.2),
    (r"^SOT-23", 1.45),
    (r"^JST_SH_SM\d+B-SRSS-TB", 2.95),
    (r"^Sensirion_DFN", 0.5),
]
# switch footprints that are not the 6 x 6 type
SWITCH_TYPES = [(r"XKB_TS-1187A", "ts-1187a")]
DEFAULT_HEIGHT = 2.0

# mounting hole drill (mm) -> screw
SCREWS = [(2.4, "M2"), (2.9, "M2.5"), (3.6, "M3")]

FAB_LAYERS = ("F.Fab", "F.CrtYd")


class KicadError(ValueError):
    pass


def _rot(x, y, deg):
    """KiCad rotation: positive angles turn counter-clockwise on screen (y points down)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def _at(node):
    at = child(node, "at")
    v = floats(at) if at else [0.0, 0.0]
    return v[0], v[1], (v[2] if len(v) > 2 else 0.0)


def _circle_center(p1, p2, p3):
    (ax, ay), (bx, by), (cx, cy) = p1, p2, p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy


def _pt(node, name):
    return tuple(floats(child(node, name))[:2])


def read_outline(pcb):
    """Bounding box (x0, y0, x1, y1) in KiCad coordinates, corner radius, warnings."""
    xs, ys, radii, warnings = [], [], [], []
    slanted = False
    for kind in ("gr_rect", "gr_line", "gr_arc", "gr_circle", "gr_poly"):
        for g in children(pcb, kind):
            if value(g, "layer") != "Edge.Cuts":
                continue
            if kind in ("gr_rect", "gr_line"):
                (x0, y0), (x1, y1) = _pt(g, "start"), _pt(g, "end")
                xs += [x0, x1]
                ys += [y0, y1]
                if kind == "gr_line" and abs(x0 - x1) > 1e-6 and abs(y0 - y1) > 1e-6:
                    slanted = True
            elif kind == "gr_arc":
                p = [_pt(g, "start"), _pt(g, "mid"), _pt(g, "end")]
                c = _circle_center(*p)
                if c is not None:
                    r = math.dist(c, p[0])
                    radii.append(r)
                    # extreme points of a quarter-circle corner are its end points
                    xs += [q[0] for q in p]
                    ys += [q[1] for q in p]
            elif kind == "gr_circle":
                raise KicadError("round board outlines are not supported")
            else:
                for xy in children(child(g, "pts"), "xy"):
                    xs.append(float(xy[1]))
                    ys.append(float(xy[2]))
                slanted = True
    if not xs:
        raise KicadError("no board outline on Edge.Cuts")
    if slanted:
        warnings.append("board outline is not a rectangle: using its bounding box")
    r = round(min(radii), 3) if radii else 0.0
    return (min(xs), min(ys), max(xs), max(ys)), r, warnings


def _fp_name(fp):
    full = fp[1] if len(fp) > 1 and isinstance(fp[1], str) else ""
    return full.split(":", 1)[-1], full


def _reference(fp):
    for p in children(fp, "property"):
        if len(p) > 2 and p[1] == "Reference":
            return p[2]
    for t in children(fp, "fp_text"):
        if len(t) > 2 and t[1] == "reference":
            return t[2]
    return "?"


def _local_points(fp):
    """Outline points of a footprint in its own frame: F.Fab, else courtyard, else pads."""
    for layer in FAB_LAYERS:
        pts = []
        for kind in ("fp_line", "fp_rect"):
            for g in children(fp, kind):
                if value(g, "layer") == layer:
                    (x0, y0), (x1, y1) = _pt(g, "start"), _pt(g, "end")
                    pts += [(x0, y0), (x1, y1), (x0, y1), (x1, y0)] if kind == "fp_rect" \
                        else [(x0, y0), (x1, y1)]
        for g in children(fp, "fp_circle"):
            if value(g, "layer") == layer:
                (cx, cy), (ex, ey) = _pt(g, "center"), _pt(g, "end")
                r = math.dist((cx, cy), (ex, ey))
                pts += [(cx - r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx + r, cy - r)]
        if pts:
            return pts, layer
    pts = []
    for pad in children(fp, "pad"):
        x, y, _ = _at(pad)
        sx, sy = (floats(child(pad, "size")) + [0, 0])[:2]
        pts += [(x - sx / 2, y - sy / 2), (x + sx / 2, y + sy / 2)]
    return pts, "pads"


def _classify(name):
    for pattern, kind in RULES:
        if re.search(pattern, name):
            return kind
    return None


def _height(name):
    for pattern, h in HEIGHTS:
        if re.search(pattern, name):
            return h
    return None


def read_board(path, name=None):
    """Return (board dict in YAML format, list of warnings, footprint list for plots)."""
    path = Path(path)
    pcb = parse(path.read_text(encoding="utf-8"))
    if not pcb or pcb[0] != "kicad_pcb":
        raise KicadError(f"{path.name}: not a KiCad board file")
    (bx0, by0, bx1, by1), corner_r, warnings = read_outline(pcb)
    px, py = bx1 - bx0, by1 - by0
    thickness = float(value(child(pcb, "general") or [], "thickness", 1.6))

    def to_board(x, y):
        return round(x - bx0, 3), round(by1 - y, 3)

    holes, comps, drills, footprints = [], [], [], []
    for fp in children(pcb, "footprint") + children(pcb, "module"):
        short, full = _fp_name(fp)
        ref = _reference(fp)
        fx, fy, rot = _at(fp)
        kind = _classify(short)
        local, source = _local_points(fp)
        world = [_rot(x, y, rot) for x, y in local]
        world = [to_board(fx + x, fy + y) for x, y in world]
        bx = [p[0] for p in world] or [to_board(fx, fy)[0]]
        by = [p[1] for p in world] or [to_board(fx, fy)[1]]
        box = (min(bx), min(by), max(bx), max(by))
        cx, cy = to_board(fx, fy)
        # body centre: footprint origins are often a pin, not the middle of the part
        mx, my = round((box[0] + box[2]) / 2, 3), round((box[1] + box[3]) / 2, 3)
        footprints.append(dict(ref=ref, name=full, kind=kind, box=box, at=(cx, cy),
                               layer=value(fp, "layer")))
        if kind == "hole":
            d = None
            for pad in children(fp, "pad"):
                dr = child(pad, "drill")
                if dr:
                    d = floats(dr)[0]
            if d is None:
                warnings.append(f"{ref}: mounting hole without drill, skipped")
                continue
            holes.append([cx, cy])
            drills.append(d)
            continue
        if value(fp, "layer") == "B.Cu":
            if kind not in ("ignore", None):
                warnings.append(f"{ref} ({short}): on the bottom side, not supported, skipped")
            continue
        if kind == "ignore":
            continue
        c = dict(ref=ref)
        if kind in CONNECTORS:
            # the edge it sticks out of: smallest distance from its outline to that edge
            reach = {"left": -box[0], "right": box[2] - px, "front": -box[1], "back": box[3] - py}
            side = max(reach, key=reach.get)
            if reach[side] < -3.0:
                warnings.append(f"{ref} ({short}): {kind} is not at a board edge, skipped")
                continue
            along = (box[1] + box[3]) / 2 if side in ("left", "right") else (box[0] + box[2]) / 2
            c.update(type=kind, side=side, pos=round(along, 2),
                     overhang=round(max(0.0, reach[side]), 2))
        elif kind == "led":
            c.update(type="led", x=mx, y=my)
        elif kind == "button":
            c.update(type="button", x=mx, y=my, dir="+x" if mx < px / 2 else "-x")
            sw = next((s for pat, s in SWITCH_TYPES if re.search(pat, short)), None)
            if sw:
                c["switch"] = sw
        elif kind == "cap":
            m = re.search(r"Elec_([\d.]+)x([\d.]+)", short)
            if m:
                c.update(type="cap", x=mx, y=my, dia=float(m.group(1)), h=float(m.group(2)))
            else:
                h = _height(short) or DEFAULT_HEIGHT
                warnings.append(f"{ref} ({short}): capacitor size not in the name, "
                                f"height {h} mm assumed")
                c.update(type="cap", x=mx, y=my, dia=round(box[2] - box[0], 2), h=h)
        else:
            h = _height(short)
            t = kind if kind in ("module", "header") else "sensor"
            if h is None:
                h = DEFAULT_HEIGHT
                warnings.append(f"{ref} ({short}): unknown height, {h} mm assumed "
                                f"(set it in the overrides file)")
            w, d = round(box[2] - box[0], 2), round(box[3] - box[1], 2)
            if t == "sensor":
                c.update(type="sensor", x=round((box[0] + box[2]) / 2, 2),
                         y=round((box[1] + box[3]) / 2, 2), w=w, d=d, h=h)
            else:
                c.update(type=t, x=round(box[0], 2), y=round(box[1], 2), w=w, d=d, h=h)
        if source == "pads" and c["type"] not in ("led", "button", "cap"):
            warnings.append(f"{ref}: no F.Fab or courtyard outline, size taken from the pads")
        comps.append(c)

    board = {
        "size": [round(px, 3), round(py, 3)],
        "thickness": thickness,
        "corner_radius": corner_r,
        "holes": holes,
    }
    if drills:
        d = min(drills)
        screw = next((s for limit, s in SCREWS if d <= limit), None)
        if screw is None:
            screw = "M3"
            warnings.append(f"mounting hole drill {d:g} mm is larger than for M3; using M3")
        board["screw"] = screw
    data = {"name": name or path.stem, "title": f"{path.stem} (from KiCad)", "board": board,
            "components": comps}
    return data, warnings, footprints


def component_height(c):
    t = c["type"]
    if t in CONNECTORS:
        return CONNECTORS[t]["h"] + c.get("z", 0.0)
    if t == "button":
        return SWITCHES[c.get("switch", "6x6")]["h"]
    if t in ("keepout", "post"):
        return 0.0
    return c.get("h", 0.0)


def auto_layout(data, hook_window=6.8, corner_margin=8.0, clearance=1.0):
    """Fill in what the board file doesn't say: design height and snap hook positions.

    Hooks go on the front and back edges, one per side on short boards, two on longer
    ones, moved along the edge until their window clears every opening on that side."""
    board = data["board"]
    comps = data["components"]
    if "component_height" not in board:
        top = max((component_height(c) for c in comps), default=3.0)
        board["component_height"] = math.ceil(top * 2) / 2
    if "snap_hooks" in data:
        return
    px = board["size"][0]
    hooks = {}
    for side in ("front", "back"):
        blocked = []
        for c in comps:
            if c.get("side") == side:
                if c["type"] in CONNECTORS:
                    half = CONNECTORS[c["type"]]["w"] / 2 + 3.0  # opening, clearance, recess
                else:  # vent
                    half = ((c["n"] - 1) * c["pitch"] + c["w"]) / 2
                blocked.append((c["pos"] - half, c["pos"] + half))
        want = [px / 2] if px < 60 else [0.15 * px, 0.85 * px]
        chosen = []
        for target in want:
            best = None
            for step in range(0, int(px * 2)):
                for cand in (target + step * 0.5, target - step * 0.5):
                    a, b = cand - hook_window / 2, cand + hook_window / 2
                    if a < corner_margin or b > px - corner_margin:
                        continue
                    if any(a < hi + clearance and b > lo - clearance for lo, hi in blocked):
                        continue
                    if any(abs(cand - x) < hook_window + 4 for x in chosen):
                        continue
                    best = cand
                    break
                if best is not None:
                    break
            if best is not None:
                chosen.append(round(best, 1))
        if chosen:
            hooks[side] = chosen
    data["snap_hooks"] = hooks


def apply_overrides(data, overrides):
    """Merge an overrides mapping into board data read from KiCad.

    Keys: ignore (list of references), parts ({ref: {key: value}}), add (extra
    components, e.g. vents), board ({key: value}), plus any top-level key of a board
    file (title, snap_hooks, button, wall_mount, shell, clearance, hook, ...)."""
    if not overrides:
        return data
    ov = dict(overrides)
    ignore = set(ov.pop("ignore", []) or [])
    parts = ov.pop("parts", {}) or {}
    add = ov.pop("add", []) or []
    data["components"] = [c for c in data["components"] if c.get("ref") not in ignore]
    for c in data["components"]:
        if c.get("ref") in parts:
            c.update(parts[c["ref"]])
    known = {c.get("ref") for c in data["components"]} | ignore
    missing = set(parts) - known
    if missing:
        raise KicadError(f"overrides: unknown reference(s) {', '.join(sorted(missing))}")
    data["components"] += [dict(c) for c in add]
    data["board"].update(ov.pop("board", {}) or {})
    data.update(ov)
    return data
