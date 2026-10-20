"""Files: STEP, STL and 3MF per part in print orientation, parameter table, check report,
and meshes in assembly position for rendering."""

import json
from collections import Counter
from pathlib import Path

from build123d import Axis, Compound, Keep, Mesher, Plane, Pos, export_step, export_stl

from .checks import as_dicts, passed, printed_upside_down
from .specs import CONNECTORS


def print_orient(name, solid):
    """Base as built; lid and light pipes flipped (top face on the bed), cap upside down."""
    s = solid.rotate(Axis.X, 180) if printed_upside_down(name) else solid
    bb = s.bounding_box()
    return s.moved(Pos(-bb.center().X, -bb.center().Y, -bb.min.Z))


def write_parts(parts, out: Path, formats=("step", "stl", "3mf")):
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, s in parts.items():
        if not s.is_valid:
            raise RuntimeError(f"{name}: invalid solid")
        po = print_orient(name, s)
        if "step" in formats:
            export_step(po, str(out / f"{name}.step"))
            written.append(out / f"{name}.step")
        if "stl" in formats:
            export_stl(po, str(out / f"{name}.stl"), tolerance=0.01, angular_tolerance=0.2)
            written.append(out / f"{name}.stl")
        if "3mf" in formats:
            m = Mesher()
            m.add_shape(po, linear_deflection=0.01, angular_deflection=0.2)
            m.write(str(out / f"{name}.3mf"))
            written.append(out / f"{name}.3mf")
    return written


def _component_groups(bodies, keep=None):
    groups = {"metal": [], "black": [], "led": []}
    for name, b in bodies.items():
        t = name.split("-")[0]
        if keep is not None:
            b = keep(b)
            if b is None:
                continue
        key = "metal" if t in ("usb", "module") else "led" if t == "led" else "black"
        groups[key].append(b)
    return groups


def write_render_meshes(parts, pcb, bodies, out: Path):
    """STL in assembly position, for render/render.py."""
    out.mkdir(parents=True, exist_ok=True)
    for name, s in parts.items():
        export_stl(s, str(out / f"{name}.stl"), tolerance=0.01, angular_tolerance=0.2)
    export_stl(pcb, str(out / "board.stl"))
    for key, bs in _component_groups(bodies).items():
        if bs:
            export_stl(Compound(children=bs), str(out / f"components-{key}.stl"))


def write_section_meshes(enc, parts, pcb, bodies, out: Path):
    """Assembly cut at the first snap hook on the front (plane x = hook position)."""
    side = "front" if enc.p.hooks.get("front") else next(iter(enc.p.hooks))
    x0 = enc.w(enc.p.hooks[side][0], 0).X
    plane = Plane(origin=(x0, 0, 0), z_dir=(1, 0, 0))
    out.mkdir(parents=True, exist_ok=True)

    def cut(s):
        c = s.split(plane, keep=Keep.TOP)
        if isinstance(c, list):
            c = Compound(children=c) if c else None
        return c if c is not None and c.volume > 1e-6 else None

    for name, s in {**parts, "board": pcb}.items():
        c = cut(s)
        if c is not None:
            export_stl(c, str(out / f"{name}.stl"), tolerance=0.01, angular_tolerance=0.2)
    for key, bs in _component_groups(bodies, keep=cut).items():
        if bs:
            export_stl(Compound(children=bs), str(out / f"components-{key}.stl"))
    (out / "section.json").write_text(json.dumps({"x": x0}))
    return x0


PARAM_ROWS = [
    ("Board (mm)", lambda e: f"{e.p.pcb[0]:g} x {e.p.pcb[1]:g} x {e.p.pcb_t:g}"),
    ("Mounting", lambda e: f"{len(e.p.holes)} x {e.p.screw}, insert Ø{e.ins['hole']:g}"
                           f" x {e.ins['depth']:g}"),
    ("Component height (mm)", lambda e: f"{e.p.comp_h:g}"),
    ("Openings", lambda e: ", ".join(
        (f"{n} x " if n > 1 else "") + k for k, n in Counter(
            c["type"] + " " + c.get("side", "top") for c in e.p.parts
            if c["type"] in CONNECTORS or c["type"] in ("vent", "led", "button")).items()) or "-"),
    ("Wall / floor / lid (mm)", lambda e: f"{e.p.wall:g} / {e.p.floor:g} / {e.p.lid_t:g}"),
    ("Clearance board / lid / connectors (mm)",
     lambda e: f"{e.p.pcb_gap:g} / {e.p.fit:g} / {e.p.cut_clear:g}"),
    ("Snap hooks", lambda e: f"{sum(len(v) for v in e.p.hooks.values())} x, L {e.hook_L:.1f}, "
                             f"t {e.p.hook_t:g}, barb {e.p.hook_d:g}"),
    ("Button", lambda e: ("-" if not e.parts_by("button") else
                          "flexure in the lid" if e.p.button == "flex" else "separate cap")),
    ("Wall mount", lambda e: f"{len(e.p.keyholes)} keyholes" if e.p.keyholes else "-"),
    ("Outside (mm)", lambda e: f"{e.out_x:.1f} x {e.out_y:.1f} x {e.H + e.p.lid_t:.1f}"),
]


def param_table(encs):
    head = "| Parameter | " + " | ".join(e.p.name.upper() for e in encs) + " |"
    lines = [head, "| --- |" + " --- |" * len(encs)]
    for label, f in PARAM_ROWS:
        lines.append(f"| {label} | " + " | ".join(f(e) for e in encs) + " |")
    return "\n".join(lines)


def outside(enc):
    return (round(enc.out_x, 2), round(enc.out_y, 2), round(enc.H + enc.p.lid_t, 2))


def write_report(enc, checks, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    data = {
        "name": enc.p.name,
        "title": enc.p.title,
        "outside_mm": outside(enc),
        "passed": passed(checks),
        "notes": enc.notes,
        "checks": as_dicts(checks),
    }
    (out / "checks.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    md = [f"# {enc.p.title or enc.p.name}", "", "Generated file, do not edit.", "",
          param_table([enc]), "", "## Checks", ""]
    md += [f"- {n}" for n in enc.notes]
    md += [f"- {c.line()}" for c in checks]
    md.append("")
    md.append("All checks passed." if passed(checks) else "**Some checks failed.**")
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
