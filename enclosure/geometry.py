"""Enclosure geometry.

Assembly coordinates: x length, y depth, z height; centre of the cavity at
x = y = 0, bottom at z = 0. Board coordinates (px, py) start at the board's
front left corner.

Parts:
- base: bosses for heat-set inserts (also the board standoffs), connector
  cutouts, windows for the snap hooks, optional keyholes for wall mounting
- lid: centring lip, snap hooks (cantilever with lead-in and 45° retention
  face), light pipe sleeves, button as a flexure in the lid or as a cap
- one light pipe per LED, optional button cap
"""

import math

from build123d import (
    Axis,
    Box,
    Circle,
    Cylinder,
    Face,
    Plane,
    Polygon,
    Pos,
    Rectangle,
    RectangleRounded,
    SlotOverall,
    Vector,
    Wire,
    chamfer,
    extrude,
    loft,
    offset,
)

from . import snapfit
from .config import Params
from .specs import CONNECTORS, INSERTS, LED, SWITCH

SIDES = {
    "left": Vector(-1, 0, 0), "right": Vector(1, 0, 0),
    "front": Vector(0, -1, 0), "back": Vector(0, 1, 0),
}


def cyl(x, y, z0, r, h):
    """Vertical cylinder centred at (x, y), from z0 to z0 + h."""
    return Pos(x, y, z0 + h / 2) * Cylinder(r, h)


def rrect(x, y, r, h, z0=0.0):
    """Rounded box, footprint centred, from z0 to z0 + h."""
    sk = RectangleRounded(x, y, r) if r > 0.01 else Rectangle(x, y)
    return extrude(Pos(0, 0, z0) * sk, h)


class Enclosure:
    def __init__(self, p: Params):
        self.p = p
        self.notes = []
        self.parts = [dict(c) for c in p.parts]  # working copies, annotated below
        px, py = p.pcb
        self.ins = INSERTS[p.screw]
        # hook length from the strain target; deflection = barb overlap
        self.hook_y = p.hook_d - p.fit
        self.lead_h = p.hook_d / math.tan(math.radians(p.hook_lead_deg))
        self.hook_L = snapfit.hook_length(p.hook_t, self.hook_y, p.strain_target)
        self.hook_len = self.hook_L + self.lead_h + p.hook_land
        self.pcb_top = p.floor + p.standoff_h + p.pcb_t
        self.H = self.pcb_top + p.comp_h + p.lid_gap  # top of base = underside of lid
        room = self.H - self.pcb_top - 0.5
        g = {s: p.pcb_gap for s in SIDES}
        for c in self.parts:
            if c["type"] in CONNECTORS:
                g[c["side"]] = max(g[c["side"]], c["overhang"] + 0.1)
        # hooks above the board, or beside it if they are too long
        self.hooks_beside = self.hook_len > room
        if self.hooks_beside:
            need = p.fit + p.hook_t + self.hook_y + 0.3
            for s in p.hooks:
                g[s] = max(g[s], need)
            self.notes.append(f"hooks {self.hook_len:.1f} mm do not fit above the board "
                              f"({room:.1f} mm free): cavity widened to {need:.2f} mm per side")
        # keep it symmetric, board centred
        gx = max(g["left"], g["right"])
        gy = max(g["front"], g["back"])
        self.gap = {"left": gx, "right": gx, "front": gy, "back": gy}
        self.in_x = px + 2 * gx
        self.in_y = py + 2 * gy
        self.out_x = self.in_x + 2 * p.wall
        self.out_y = self.in_y + 2 * p.wall
        # inner corner radius small enough to clear the board corner (arc in arc)
        gmin = min(gx, gy)
        r_fit = (math.sqrt(2) * (gmin + p.pcb_r) - p.pcb_r - 0.3) / (math.sqrt(2) - 1)
        self.r_in = max(0.5, min(p.corner_r - p.wall, r_fit))
        self.ox, self.oy = -px / 2, -py / 2  # board -> assembly
        self.flex_L = self.flex_y = None
        self.cap_z = None
        self.keyhole_pad_top = None

    def parts_by(self, t):
        return [c for c in self.parts if c["type"] == t]

    # ---------- helpers ----------
    def w(self, x, y):
        return Vector(x + self.ox, y + self.oy)

    def wxy(self, x, y):
        return (x + self.ox, y + self.oy)

    def wall_plane(self, side, along, z, u=0.0):
        """Plane in the wall: origin on the inner face (+u outwards), x along the wall, y = z."""
        n = SIDES[side]
        if side in ("left", "right"):
            o = Vector(n.X * self.in_x / 2, along + self.oy, z)
        else:
            o = Vector(along + self.ox, n.Y * self.in_y / 2, z)
        o = o + n * u
        return Plane(origin=o, x_dir=Vector(0, 0, 1).cross(n), z_dir=n)

    def edge_offset(self, side):
        return {"left": 0.0, "front": 0.0, "right": self.p.pcb[0], "back": self.p.pcb[1]}[side]

    @staticmethod
    def opening_sketch(kind, w, h):
        if kind == "stadium":
            return SlotOverall(w, h)
        if kind == "round":  # teardrop with a 45° roof, printable without support
            r = w / 2
            roof = Polygon((-r * 0.7071, r * 0.7071), (r * 0.7071, r * 0.7071), (0, r * 1.4142))
            return Circle(r) + roof
        if kind == "vslot":  # vertical slot, round bottom, 45° top
            r = w / 2
            roof = Polygon((-r, h / 2 - r), (r, h / 2 - r), (0, h / 2))
            return Pos(0, -(h / 2 - r)) * Circle(r) + Rectangle(w, h - 2 * r) + roof
        return RectangleRounded(w, h, min(0.8, h / 2 - 0.01))

    # ---------- board and components ----------
    def board(self):
        p = self.p
        px, py = p.pcb
        z0 = p.floor + p.standoff_h
        pcb = rrect(px, py, p.pcb_r, p.pcb_t, z0)
        for hx, hy in p.holes:
            c = self.w(hx, hy)
            pcb -= cyl(c.X, c.Y, z0 - 1, 1.4 if p.screw == "M2.5" else 1.7, 5)
        bodies = {}
        zt = self.pcb_top
        for i, c in enumerate(self.parts):
            t = c["type"]
            if t in CONNECTORS:
                spec = CONNECTORS[t]
                outward = 1 if c["side"] in ("right", "back") else -1
                face = self.edge_offset(c["side"]) + outward * c["overhang"]
                center_in = face - outward * spec["d"] / 2
                if c["side"] in ("left", "right"):
                    pos = self.w(center_in, c["pos"])
                    b = Box(spec["d"], spec["w"], spec["h"])
                else:
                    pos = self.w(c["pos"], center_in)
                    b = Box(spec["w"], spec["d"], spec["h"])
                body = Pos(pos.X, pos.Y, zt + c["z"] + spec["h"] / 2) * b
                c["_face"] = face
            elif t in ("module", "header"):
                body = Pos(*self.wxy(c["x"] + c["w"] / 2, c["y"] + c["d"] / 2),
                           zt + c["h"] / 2) * Box(c["w"], c["d"], c["h"])
            elif t == "sensor":
                body = Pos(*self.wxy(c["x"], c["y"]), zt + c["h"] / 2) * Box(c["w"], c["d"], c["h"])
            elif t == "cap":
                q = self.w(c["x"], c["y"])
                body = cyl(q.X, q.Y, zt, c["dia"] / 2, c["h"])
            elif t == "led":
                body = Pos(*self.wxy(c["x"], c["y"]), zt + LED["h"] / 2) * Box(
                    LED["w"], LED["d"], LED["h"])
            elif t == "button":
                s = SWITCH
                body = Pos(*self.wxy(c["x"], c["y"]), zt + s["body_h"] / 2) * Box(
                    s["w"], s["w"], s["body_h"])
                q = self.w(c["x"], c["y"])
                body += cyl(q.X, q.Y, zt + s["body_h"] - 0.01, s["plunger_d"] / 2,
                            s["h"] - s["body_h"] + 0.01)
            else:
                continue
            bodies[f"{t}-{i}"] = body
        return pcb, bodies

    def u_face(self, c):
        """Connector face relative to the inner wall face (negative = inside)."""
        return abs(c["_face"] - self.edge_offset(c["side"])) - self.gap[c["side"]]

    def mating(self):
        """Plug envelopes: the connector's opening profile from its face outwards, plus the
        plug overmold from where it can reach."""
        p = self.p
        env = {}
        for i, c in enumerate(self.parts):
            if c["type"] not in CONNECTORS:
                continue
            spec = CONNECTORS[c["type"]]
            side = c["side"]
            z = self.pcb_top + c["z"] + spec["zc"]
            u_face = self.u_face(c)
            kind, ow, oh = spec["opening"]
            sk = Circle(ow / 2) if kind == "round" else self.opening_sketch(kind, ow, oh)
            e = extrude(self.wall_plane(side, c["pos"], z, u_face) * sk, p.wall + 6)
            dist_out = p.wall - u_face  # connector face to outer surface
            if spec["overmold"] and dist_out > spec["reach"]:
                mw, mh = spec["overmold"]
                # starts 0.5 mm in front of the recess bottom: measures the side clearance
                pl2 = self.wall_plane(side, c["pos"], z, u_face + spec["reach"] + 0.5)
                env[f"plug-{c['type']}-{i}-overmold"] = extrude(
                    pl2 * RectangleRounded(mw, mh, mh / 2 - 0.01), 10)
            env[f"plug-{c['type']}-{i}"] = e
            c["_dist_out"] = dist_out
        return env

    # ---------- snap hooks ----------
    def hook_profile(self, side, along, grow=0.0, shift_u=0.0):
        """Hook as a profile (u outwards, z), extruded along the wall."""
        p = self.p
        H = self.H
        uo = -p.fit + shift_u
        ui = uo - p.hook_t
        zt = H - self.hook_len
        zr = zt + self.lead_h + p.hook_land + p.hook_d  # top of the retention face
        rf = 0.6  # root fillet, approximated by a polygon
        pts = [
            (uo, H + p.lid_t / 2), (uo, zr), (uo + p.hook_d, zr - p.hook_d),
            (uo + p.hook_d, zt + self.lead_h), (uo, zt), (ui, zt), (ui, H - rf),
            (ui - rf * 0.29, H - rf * 0.29), (ui - rf, H), (ui - rf, H + p.lid_t / 2),
        ]
        return self._prism(side, along, pts, p.hook_w + 2 * grow)

    def _prism(self, side, along, pts, width):
        pl = self.wall_plane(side, along, 0.0)
        n = SIDES[side]
        t = pl.x_dir
        base = pl.origin
        world = [base + n * u + Vector(0, 0, z) - t * (width / 2) for u, z in pts]
        return extrude(Face(Wire.make_polygon(world, close=True)), amount=width, dir=t)

    def window_profile(self, side, along):
        p = self.p
        H = self.H
        uo = -p.fit
        zt = H - self.hook_len
        zr = zt + self.lead_h + p.hook_land + p.hook_d
        # roof parallel to the retention face, hook_play higher; falls 45° outwards
        zc = lambda u: zr + p.hook_play - (u - uo)  # noqa: E731
        u0, u1 = -0.6, p.wall + 1.0
        z_floor = min(zt - 0.3, zc(p.wall) - 1.2)
        pts = [(u0, z_floor), (u1, z_floor), (u1, zc(u1)), (u0, zc(u0))]
        self.win_z = (z_floor, zc(0.0))
        return self._prism(side, along, pts, p.hook_w + 0.8)

    # ---------- parts ----------
    def base(self):
        p = self.p
        H = self.H
        outer = rrect(self.out_x, self.out_y, p.corner_r, H)
        outer = chamfer(outer.edges().group_by(Axis.Z)[0], p.bed_chamfer)
        outer = chamfer(outer.edges().group_by(Axis.Z)[-1], p.parting_chamfer)
        cav = rrect(self.in_x, self.in_y, self.r_in, H, p.floor)
        lead = loft([Pos(0, 0, H - 0.5) * RectangleRounded(self.in_x, self.in_y, self.r_in),
                     Pos(0, 0, H + 0.001) * RectangleRounded(self.in_x + 1, self.in_y + 1,
                                                             self.r_in + 0.5)])
        part = outer - cav - lead - rrect(self.in_x + 1, self.in_y + 1, self.r_in + 0.5, 2, H)
        # bosses with heat-set insert hole and lead-in chamfer
        for hx, hy in p.holes:
            c = self.w(hx, hy)
            part += cyl(c.X, c.Y, p.floor - 0.01, self.ins["boss"] / 2, p.standoff_h + 0.01)
            top = p.floor + p.standoff_h
            part -= Pos(c.X, c.Y, top - self.ins["depth"] / 2) * Cylinder(
                self.ins["hole"] / 2, self.ins["depth"] + 0.02)
            part -= loft([Pos(c.X, c.Y, top - 0.4) * Circle(self.ins["hole"] / 2),
                          Pos(c.X, c.Y, top + 0.01) * Circle(self.ins["hole"] / 2 + 0.41)])
        # keyholes: head Ø8.5, shank 4.5, for a 4 mm round head screw
        for kx in p.keyholes:
            lip, pocket, roof = 1.6, 2.6, 1.2
            slot = 8.0
            pad_h = lip + pocket + roof
            part += Pos(kx, slot / 2, 0) * extrude(SlotOverall(slot + 8.5 + 3.2, 8.5 + 3.2,
                                                                rotation=90), pad_h)
            part -= cyl(kx, 0, -0.1, 4.25, lip + 0.2)
            part -= Pos(kx, slot / 2, -0.1) * extrude(SlotOverall(slot + 4.5, 4.5, rotation=90),
                                                      lip + 0.2)
            part -= Pos(kx, slot / 2, lip) * extrude(SlotOverall(slot + 8.5, 8.5, rotation=90),
                                                     pocket)
            self.keyhole_pad_top = pad_h
        for side, xs in p.hooks.items():
            for hx in xs:
                part -= self.window_profile(side, hx)
        # openings: (side, label, start, end, bottom, top) along the wall, for the web check
        self.openings = []
        for c in self.parts:
            t = c["type"]
            if t in CONNECTORS:
                spec = CONNECTORS[t]
                kind, ow, oh = spec["opening"]
                z = self.pcb_top + c["z"] + spec["zc"]
                ow2, oh2 = ow + 2 * p.cut_clear, oh + 2 * p.cut_clear
                sk = self.opening_sketch(kind, ow2, oh2)
                part -= extrude(self.wall_plane(c["side"], c["pos"], z, -1.0) * sk, p.wall + 2)
                top = z + (oh2 / 2 * 1.4142 if kind == "round" else oh2 / 2)
                self.openings.append((c["side"], t, c["pos"] - ow2 / 2, c["pos"] + ow2 / 2,
                                      z - oh2 / 2, top))
                # plug recess outside, where the wall in front of the connector is too thick
                u_face = self.u_face(c)
                if spec["overmold"] and p.wall - u_face > spec["reach"]:
                    mw, mh = spec["overmold"]
                    mw, mh = mw + 2 * p.cut_clear, mh + 2 * p.cut_clear
                    depth = p.wall - u_face - spec["reach"]
                    pl = self.wall_plane(c["side"], c["pos"], z, p.wall - depth)
                    part -= extrude(pl * RectangleRounded(mw, mh, min(2.0, mh / 2 - 0.01)),
                                    depth + 1)
                    c["_recess"] = (depth, p.wall - depth)
                    self.openings.append((c["side"], f"{t} recess", c["pos"] - mw / 2,
                                          c["pos"] + mw / 2, z - mh / 2, z + mh / 2))
            elif t == "vent":
                z = self.pcb_top + c["z"] + c["h"] / 2
                n = c["n"]
                for k in range(n):
                    a = c["pos"] + (k - (n - 1) / 2) * c["pitch"]
                    sk = self.opening_sketch("vslot", c["w"], c["h"])
                    part -= extrude(self.wall_plane(c["side"], a, z, -1.0) * sk, p.wall + 2)
                span = (n - 1) * c["pitch"] + c["w"]
                self.openings.append((c["side"], "vent", c["pos"] - span / 2,
                                      c["pos"] + span / 2, z - c["h"] / 2, z + c["h"] / 2))
        for side, xs in p.hooks.items():
            for hx in xs:
                self.openings.append((side, "hook window", hx - (p.hook_w + 0.8) / 2,
                                      hx + (p.hook_w + 0.8) / 2, *self.win_z))
        return part

    def lid(self, board_bodies):
        p = self.p
        H = self.H
        plate = rrect(self.out_x, self.out_y, p.corner_r, p.lid_t, H)
        plate = chamfer(plate.edges().group_by(Axis.Z)[-1], p.bed_chamfer)
        plate = chamfer(plate.edges().group_by(Axis.Z)[0], p.parting_chamfer)
        lx, ly, lr = self.in_x - 2 * p.fit, self.in_y - 2 * p.fit, max(0.3, self.r_in - p.fit)
        lip = rrect(lx, ly, lr, p.lip_h + 0.01, H - p.lip_h) - rrect(
            lx - 2 * p.lip_w, ly - 2 * p.lip_w, max(0.2, lr - p.lip_w), p.lip_h + 1,
            H - p.lip_h - 0.5)
        # interrupt the lip at the hooks
        for side, xs in p.hooks.items():
            for hx in xs:
                if side in ("front", "back"):
                    c = self.w(hx, 0)
                    cut = Pos(c.X, SIDES[side].Y * self.in_y / 2, H - p.lip_h / 2) * Box(
                        p.hook_w + 2.0, 6.0, p.lip_h + 1)
                else:
                    c = self.w(0, hx)
                    cut = Pos(SIDES[side].X * self.in_x / 2, c.Y, H - p.lip_h / 2) * Box(
                        6.0, p.hook_w + 2.0, p.lip_h + 1)
                lip -= cut
        # cut the lip where components stand up into it (0.5 mm clearance)
        cut_for = []
        for name, b in board_bodies.items():
            bb = b.bounding_box()
            if bb.max.Z > H - p.lip_h - 0.5:
                keep = Pos(*bb.center()) * Box(bb.size.X + 1.0, bb.size.Y + 1.0, bb.size.Z + 1.0)
                if (lip & keep).volume > 1e-6:
                    lip -= keep
                    cut_for.append(name)
        if cut_for:
            self.notes.append("lid lip cut out above: " + ", ".join(cut_for))
        lid = plate + lip
        for side, xs in p.hooks.items():
            for hx in xs:
                lid += self.hook_profile(side, hx)
        top_z = H + p.lid_t
        for c in self.parts_by("led"):
            cpos = self.w(c["x"], c["y"])
            d = p.lp_d + 2 * p.lp_fit
            lid += Pos(cpos.X, cpos.Y, H - p.sleeve_h / 2 + 0.01) * Cylinder(
                d / 2 + 1.2, p.sleeve_h + 0.02)
            lid -= Pos(cpos.X, cpos.Y, top_z - 10) * Cylinder(d / 2, 30)
        for c in self.parts_by("button"):
            cpos = self.w(c["x"], c["y"])
            if p.button == "flex":
                lid = self._flex(lid, c, cpos)
            else:
                d = p.cap_d + 2 * p.cap_fit
                lid += Pos(cpos.X, cpos.Y, H - p.sleeve_h / 2 + 0.01) * Cylinder(
                    d / 2 + 1.2, p.sleeve_h + 0.02)
                lid -= Pos(cpos.X, cpos.Y, top_z - 10) * Cylinder(d / 2, 30)
        return lid

    def _flex(self, lid, c, cpos):
        p = self.p
        H = self.H
        sgn = 1 if c["dir"].startswith("+") else -1
        # tongue: round free end around the switch, root in direction `dir`
        Lf, wf, s = p.flex_len, p.flex_w, p.flex_slot
        tip_x = cpos.X - sgn * wf / 2
        root_x = tip_x + sgn * Lf
        cx = (tip_x + root_x) / 2
        tongue = Pos(cx, cpos.Y) * SlotOverall(Lf + wf / 2, wf)
        tongue = tongue - Pos(root_x + sgn * wf / 2, cpos.Y) * Rectangle(wf, wf + 4)
        tongue_f = tongue.faces()[0]
        ring = offset(tongue_f, s) - tongue_f
        ring = ring - Pos(root_x + sgn * (wf / 2 + s), cpos.Y) * Rectangle(wf + 2 * s, wf + 6)
        lid -= extrude(Pos(0, 0, H - 0.5) * ring, p.lid_t + 1)
        # thinned from inside; hinge 1 mm past the root
        pocket = Pos(cx + sgn * 0.5, cpos.Y) * Rectangle(Lf + 1.0, wf + 2 * s)
        lid -= extrude(Pos(0, 0, H - 0.01) * pocket, p.lid_t - p.flex_t + 0.01)
        # plunger down to just above the switch
        z_bot = self.pcb_top + SWITCH["h"] + p.btn_gap
        z_top = H + p.lid_t - p.flex_t + 0.01
        lid += Pos(cpos.X, cpos.Y, (z_bot + z_top) / 2) * Cylinder(2.0, z_top - z_bot)
        self.flex_L = abs(root_x + sgn * 1.0 - cpos.X)  # hinge to plunger centre
        self.flex_y = p.btn_gap + SWITCH["travel"]
        return lid

    def light_pipes(self):
        p = self.p
        pipes = []
        top = self.H + p.lid_t
        for c in self.parts_by("led"):
            cpos = self.w(c["x"], c["y"])
            z_tip = self.pcb_top + LED["h"] + p.lp_gap
            rod = Pos(cpos.X, cpos.Y, (z_tip + top) / 2) * Cylinder(p.lp_d / 2, top - z_tip)
            head = cyl(cpos.X, cpos.Y, top, p.lp_head_d / 2, p.lp_head_h)
            pipe = rod + head
            pipes.append(chamfer(pipe.edges().group_by(Axis.Z)[-1], 0.3))
        return pipes

    def button_cap(self):
        p = self.p
        if p.button != "cap":
            return None
        c = self.parts_by("button")[0]
        cpos = self.w(c["x"], c["y"])
        z_bot = self.pcb_top + SWITCH["h"]
        top = self.H + p.lid_t + p.cap_proud
        fl_r, fl_h = p.cap_d / 2 + 1.8, 0.4  # flange with a 45° cone on top: prints upside down
        cone_h = fl_r - p.cap_d / 2
        z_fl = self.H - p.sleeve_h - 0.3 - fl_h - cone_h  # flange 0.3 below the sleeve
        stem = cyl(cpos.X, cpos.Y, z_bot, 2.0, z_fl - z_bot + 0.01)
        flange = cyl(cpos.X, cpos.Y, z_fl, fl_r, fl_h)
        cone = loft([Pos(cpos.X, cpos.Y, z_fl + fl_h) * Circle(fl_r),
                     Pos(cpos.X, cpos.Y, z_fl + fl_h + cone_h) * Circle(p.cap_d / 2)])
        shaft = cyl(cpos.X, cpos.Y, z_fl + fl_h + cone_h - 0.01, p.cap_d / 2,
                    top - (z_fl + fl_h + cone_h) + 0.01)
        cap = stem + flange + cone + shaft
        cap = chamfer(cap.edges().group_by(Axis.Z)[-1], 0.6)
        self.cap_z = (z_bot, z_fl + fl_h + cone_h, top)
        return cap


def build(p: Params):
    """Build all parts. Returns (enclosure, parts, board, component bodies, plug envelopes)."""
    enc = Enclosure(p)
    pcb, bodies = enc.board()
    env = enc.mating()
    parts = {"base": enc.base(), "lid": enc.lid(bodies)}
    for i, lp in enumerate(enc.light_pipes()):
        parts[f"light-pipe-{i + 1}"] = lp
    cap = enc.button_cap()
    if cap is not None:
        parts["button-cap"] = cap
    return enc, parts, pcb, bodies, env
