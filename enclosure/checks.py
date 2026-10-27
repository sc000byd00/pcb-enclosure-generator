"""Design checks. Every check has an id, a pass/fail flag and a readable message;
info lines carry values without a limit (forces, overhang areas)."""

import math
from dataclasses import asdict, dataclass

from build123d import Cylinder, Pos

from . import snapfit
from .geometry import SIDES
from .specs import CONNECTORS, PETG


@dataclass
class Check:
    id: str
    ok: bool | None  # None = information only
    message: str

    def line(self):
        tag = {True: "PASS", False: "FAIL", None: "INFO"}[self.ok]
        return f"{tag}  {self.message}"


def overhangs(solid, flip=False):
    """Area of downward-facing triangles steeper than 45° in print orientation (mm²),
    split into horizontal (bridges) and sloped; the bed face is excluded."""
    verts, tris = solid.tessellate(0.02, 0.1)
    pts = [(v.X, v.Y, -v.Z if flip else v.Z) for v in verts]
    zmin = min(p[2] for p in pts)
    flat = slope = 0.0
    for a, b, c in tris:
        if flip:
            a, c = c, a
        A, B, C = pts[a], pts[b], pts[c]
        u = [B[i] - A[i] for i in range(3)]
        v = [C[i] - A[i] for i in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        area2 = math.sqrt(sum(x * x for x in n))
        if area2 < 1e-12:
            continue
        nz = n[2] / area2
        if (A[2] + B[2] + C[2]) / 3 < zmin + 0.02:
            continue
        if nz < -0.999:
            flat += area2 / 2
        elif nz < -0.7314:  # 2° tolerance for faceted 45° faces
            slope += area2 / 2
    return flat, slope


def boxes_touch(a, b, tol=0.01):
    """Bounding boxes intersect (build123d's BoundBox.overlaps is False when one box
    contains the other, which is the usual case for a component inside the base)."""
    a, b = a.bounding_box(), b.bounding_box()
    return all(getattr(a.min, k) <= getattr(b.max, k) + tol and
               getattr(b.min, k) <= getattr(a.max, k) + tol for k in "XYZ")


def printed_upside_down(name):
    return name in ("lid", "button-cap") or name.startswith("light-pipe")


def _bosses(enc):
    """Bosses and support posts: the board rests on them, so they are left out of the
    board-to-wall distance."""
    p = enc.p
    s = None
    supports = [(hx, hy, enc.ins["boss"] / 2) for hx, hy in p.holes]
    supports += [(c["x"], c["y"], c["dia"] / 2) for c in enc.parts_by("post")]
    for hx, hy, r in supports:
        c = enc.w(hx, hy)
        b = Pos(c.X, c.Y, p.floor + p.standoff_h / 2) * Cylinder(r + 0.01, p.standoff_h + 0.2)
        s = b if s is None else s + b
    return s


def hook_numbers(enc):
    p = enc.p
    eps = snapfit.strain(p.hook_t, enc.hook_y, enc.hook_L)
    P = snapfit.deflection_force(p.hook_w, p.hook_t, PETG["E"], eps, enc.hook_L)
    return dict(
        strain=eps,
        insert=snapfit.mating_force(P, p.hook_lead_deg, PETG["mu"]),
        remove=snapfit.mating_force(P, p.hook_ret_deg, PETG["mu"]),
        count=sum(len(v) for v in p.hooks.values()),
    )


def run(enc, parts, pcb, bodies, env, overhang=True):
    p = enc.p
    out = []

    def check(id_, cond, msg):
        out.append(Check(id_, bool(cond), msg))

    def info(id_, msg):
        out.append(Check(id_, None, msg))

    base, lid = parts["base"], parts["lid"]

    check("walls", p.wall >= p.min_wall and p.floor >= p.min_wall and p.lid_t >= p.min_wall,
          f"wall {p.wall:g}, floor {p.floor:g}, lid {p.lid_t:g} mm (min {p.min_wall:g})")

    gx, gy = enc.gap["left"], enc.gap["front"]
    check("board-fit", min(gx, gy) >= p.pcb_gap,
          f"board {p.pcb[0]:g} x {p.pcb[1]:g} in cavity {enc.in_x:.1f} x {enc.in_y:.1f}, "
          f"gap {gx:.2f} / {gy:.2f} mm")
    shell = base - _bosses(enc) if p.holes or enc.parts_by("post") else base
    d = pcb.distance_to(shell)
    check("board-wall", d >= min(p.pcb_gap, 0.3) - 0.01,
          f"board to wall at least {d:.2f} mm (inner corner radius {enc.r_in:.2f})")

    hits = []
    for name, b in list(bodies.items()) + [("board", pcb)]:
        for hn, h in parts.items():
            if not boxes_touch(b, h):
                continue
            v = (b & h).volume
            if v > 1e-3:
                hits.append(f"{name}/{hn} {v:.3f} mm3")
    check("collisions", not hits,
          "board and components clear of all enclosure parts" + (": " + ", ".join(hits)
                                                                  if hits else ""))

    if bodies:
        top = max(b.bounding_box().max.Z for b in bodies.values()) - enc.pcb_top
        check("component-height", top <= p.comp_h + 1e-6,
              f"tallest component {top:.1f} mm, design height {p.comp_h:g} mm")
        to_lid = [b.distance_to(lid) for n, b in bodies.items()
                  if not n.startswith(("button", "led"))]
        if to_lid:
            m = min(to_lid)
            check("lid-clearance", m >= min(p.lid_gap, 0.5) - 0.01,
                  f"components to lid (lip, hooks, sleeves) at least {m:.2f} mm")

    for name, e in env.items():
        dd = e.distance_to(base)
        what = "overmold in its recess" if name.endswith("overmold") else "plug in the cutout"
        check(f"plug:{name}", dd >= p.cut_clear - 0.02,
              f"{name}: {what}, {dd:.2f} mm clearance (target {p.cut_clear:g})")
    for c in enc.parts:
        if c["type"] not in CONNECTORS:
            continue
        spec = CONNECTORS[c["type"]]
        if "_recess" in c:
            dep, rest = c["_recess"]
            check(f"recess:{c['type']}@{c['pos']:g}", rest >= p.min_local - 0.01,
                  f"{c['type']}: plug recess {dep:.2f} mm deep, remaining wall {rest:.2f} mm")
        else:
            check(f"reach:{c['type']}@{c['pos']:g}", c["_dist_out"] <= spec["reach"] + 1e-6,
                  f"{c['type']}: connector face {c['_dist_out']:.2f} mm behind the outer "
                  f"surface (plug reaches {spec['reach']:g})")

    webs = []
    for side in SIDES:
        ops = sorted([o for o in enc.openings if o[0] == side], key=lambda o: o[2])
        length = enc.in_x if side in ("front", "back") else enc.in_y
        lo_lim = -(length / 2 - enc.r_in)
        off = enc.ox if side in ("front", "back") else enc.oy
        for o in ops:
            a0, a1 = o[2] + off, o[3] + off
            webs.append((min(a0 - lo_lim, -lo_lim - a1), f"{side} {o[1]} to corner"))
            webs.append((enc.H - o[5], f"{side} {o[1]} to rim"))
            webs.append((o[4] - p.floor, f"{side} {o[1]} to floor"))
        for o1, o2 in zip(ops, ops[1:]):
            if "recess" in o1[1] or "recess" in o2[1]:
                continue
            webs.append((o2[2] - o1[3], f"{side} {o1[1]} to {o2[1]}"))
    if webs:
        wmin = min(webs)
        check("webs", wmin[0] >= p.min_web - 1e-6,
              f"narrowest web {wmin[0]:.2f} mm ({wmin[1]}), min {p.min_web:g}")

    v = (lid & base).volume
    check("lid-base", v < 1e-3, f"lid does not intersect the base ({v:.4f} mm3)")

    h = hook_numbers(enc)
    check("hook-strain", h["strain"] <= PETG["strain_allow"],
          f"snap hooks: L {enc.hook_L:.1f} mm, t {p.hook_t:g}, deflection {enc.hook_y:.2f} mm "
          f"-> strain {h['strain'] * 100:.2f} % (limit {PETG['strain_allow'] * 100:.1f} %, PETG)")
    info("hook-forces", f"assembly {h['count']} x {h['insert']:.1f} = {h['count'] * h['insert']:.0f} N, "
         f"removal {h['count']} x {h['remove']:.1f} = {h['count'] * h['remove']:.0f} N "
         f"(E {PETG['E']:.0f} MPa, mu {PETG['mu']})")
    bent = []
    for side, xs in p.hooks.items():
        for hx in xs:
            env_h = enc.hook_profile(side, hx, shift_u=-enc.hook_y - 0.2)
            for name, b in list(bodies.items()) + [("board", pcb)]:
                if (env_h & b).volume > 1e-4:
                    bent.append(f"{side}@{hx:g}/{name}")
    check("hook-clearance", not bent,
          f"deflected hooks (+0.2 mm) clear of board and components, "
          f"{'beside' if enc.hooks_beside else 'above'} the board"
          + (": " + ", ".join(bent) if bent else ""))

    if p.button == "flex" and enc.parts_by("button"):
        e2 = snapfit.strain(p.flex_t, enc.flex_y, enc.flex_L)
        F = snapfit.flexure_force(PETG["E"], p.flex_w, p.flex_t, enc.flex_y, enc.flex_L)
        check("flexure", e2 <= PETG["strain_allow"],
              f"button flexure: L {enc.flex_L:.1f}, t {p.flex_t:g}, travel {enc.flex_y:.2f} mm "
              f"-> strain {e2 * 100:.2f} %, press force {F + enc.flex_sw['force']:.1f} N "
              f"(flexure {F:.1f} + switch {enc.flex_sw['force']:g})")
    if p.button == "cap" and enc.cap_z:
        _, z_fl, _ = enc.cap_z
        play = enc.H - p.sleeve_h - z_fl
        travel = enc.switch(enc.parts_by("button")[0])["travel"]
        check("button-cap", p.cap_proud > travel and play > 0.1,
              f"button cap stands {p.cap_proud:g} mm proud, travel {travel:g} mm, "
              f"flange {play:.1f} mm below the sleeve")
    for i, c in enumerate(enc.parts_by("keepout")):
        zone = enc.keepout_volume(c)
        hit = [n for n, part in parts.items() if (zone & part).volume > 1e-4]
        name = c.get("ref", f"keepout-{i + 1}")
        check(f"keepout-{i + 1}", not hit,
              f"{name}: {c['w']:g} x {c['d']:g} mm free of enclosure parts over the cavity height"
              + (": hit by " + ", ".join(hit) if hit else ""))
    for i, _ in enumerate(enc.parts_by("led")):
        check(f"light-pipe-{i + 1}", 0.2 <= p.lp_gap <= 1.0,
              f"light pipe {i + 1}: tip {p.lp_gap:g} mm above the LED, fit {p.lp_fit:g} mm")

    if p.keyholes:
        gap = (p.floor + p.standoff_h) - enc.keyhole_pad_top
        check("keyholes", gap >= p.pcb_under,
              f"keyholes: {gap:.1f} mm free under the board (min {p.pcb_under:g})")

    if overhang:
        for name, s in parts.items():
            fl, sl = overhangs(s, flip=printed_upside_down(name))
            info(f"overhang:{name}", f"overhang {name}: {sl:.1f} mm² steeper than 45°, "
                 f"{fl:.1f} mm² horizontal (bridges)")
    return out


def passed(checks):
    return all(c.ok is not False for c in checks)


def as_dicts(checks):
    return [asdict(c) for c in checks]
