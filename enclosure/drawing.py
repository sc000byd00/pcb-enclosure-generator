"""Dimensioned drawing: top view, front and left view, section through a snap hook and
boss, and a detail of the hook. Views by hidden-line projection, section from the cut faces.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

from build123d import Compound, Keep, Plane  # noqa: E402

from .checks import hook_numbers  # noqa: E402
from .geometry import build  # noqa: E402
from .specs import CONNECTORS, PETG  # noqa: E402

INK = "#1f3f8f"
DIM = "#333333"
MARK = "#c0392b"


def pts(edge, n=24):
    if getattr(edge.geom_type, "name", "") == "LINE":
        n = 1
    return [edge @ (i / n) for i in range(n + 1)]


def draw_view(ax, shape, origin, up, focus):
    vis, _ = shape.project_to_viewport(origin, up, focus)
    for e in vis:
        p = pts(e)
        ax.plot([v.X for v in p], [v.Y for v in p], color=INK, lw=0.9)
    ax.set_aspect("equal")
    ax.axis("off")


def dim(ax, a, b, off, text, vertical=False, fs=8):
    """Dimension line from a to b (view coordinates), offset by `off`."""
    s = 1 if off > 0 else -1
    if vertical:
        x = a[0] + off
        ax.annotate("", (x, a[1]), (x, b[1]), arrowprops=dict(arrowstyle="<->", lw=0.7, color=DIM))
        for p in (a, b):
            ax.plot([p[0], x + 0.8 * s], [p[1], p[1]], color=DIM, lw=0.4)
        ax.text(x + 0.8 * s, (a[1] + b[1]) / 2, text, fontsize=fs, rotation=90, va="center",
                ha="left" if off > 0 else "right", color=DIM)
    else:
        y = a[1] + off
        ax.annotate("", (a[0], y), (b[0], y), arrowprops=dict(arrowstyle="<->", lw=0.7, color=DIM))
        for p in (a, b):
            ax.plot([p[0], p[0]], [p[1], y + 0.8 * s], color=DIM, lw=0.4)
        ax.text((a[0] + b[0]) / 2, y + 0.6 * s, text, fontsize=fs, ha="center",
                va="bottom" if off > 0 else "top", color=DIM)


def section_faces(solid, x0):
    cut = solid.split(Plane(origin=(x0, 0, 0), z_dir=(1, 0, 0)), keep=Keep.TOP)
    if isinstance(cut, list):
        cut = Compound(children=cut)
    out = []
    for f in cut.faces():
        c = f.center()
        if abs(c.X - x0) < 1e-3 and abs(abs(f.normal_at().X) - 1) < 1e-6:
            outer = [(v.Y, v.Z) for e in f.outer_wire().order_edges() for v in pts(e)]
            holes = [[(v.Y, v.Z) for e in w.order_edges() for v in pts(e)]
                     for w in f.inner_wires()]
            out.append((outer, holes))
    return out


def draw_section(ax, items, x0):
    for solid, color, hatch in items:
        for outer, holes in section_faces(solid, x0):
            ax.add_patch(MplPolygon(outer, closed=True, facecolor=color, edgecolor=INK, lw=0.6,
                                    hatch=hatch))
            for h in holes:
                ax.add_patch(MplPolygon(h, closed=True, facecolor="white", edgecolor=INK, lw=0.6))
    ax.set_aspect("equal")
    ax.axis("off")


def note(ax, xy, text_xy, text, fs=7.5):
    ax.annotate(text, xy, text_xy, fontsize=fs, color=DIM, va="center",
                arrowprops=dict(arrowstyle="-", lw=0.5, color=DIM, shrinkA=0, shrinkB=0))


def draw(p, png_path, pdf_path=None, built=None):
    """Write the drawing. `built` takes the result of geometry.build(p) to avoid a rebuild."""
    enc, parts, pcb, _, _ = built or build(p)
    base, lid = parts["base"], parts["lid"]
    asm = Compound(children=list(parts.values()))
    H, T = enc.H, enc.H + p.lid_t
    ox, oy = enc.out_x / 2, enc.out_y / 2
    zf = T / 2  # side views are centred on the view axis

    fig = plt.figure(figsize=(16.5, 11.0))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.3, 1.05, 1.3], height_ratios=[1.0, 1.0],
                          left=0.03, right=0.98, top=0.9, bottom=0.04, wspace=0.12, hspace=0.12)
    ax_top = fig.add_subplot(gs[0, 0])
    ax_front = fig.add_subplot(gs[1, 0])
    ax_left = fig.add_subplot(gs[1, 1])
    ax_sec = fig.add_subplot(gs[0, 1])
    ax_det = fig.add_subplot(gs[:, 2])

    # top view, section line through the first front hook
    draw_view(ax_top, asm, (0, 0, 500), (0, 1, 0), (0, 0, 0))
    ax_top.set_title("Top view", fontsize=11)
    dim(ax_top, (-ox, -oy), (ox, -oy), -5, f"{enc.out_x:.1f}")
    dim(ax_top, (ox, -oy), (ox, oy), 5, f"{enc.out_y:.1f}", vertical=True)
    side = "front" if p.hooks.get("front") else None
    x0 = enc.w(p.hooks[side][0], 0).X if side else 0.0
    ax_top.plot([x0, x0], [-oy - 2, oy + 2], color=MARK, lw=0.8, ls="-.")
    for yy in (oy + 3, -oy - 3.5):
        ax_top.text(x0, yy, "A", color=MARK, ha="center", fontsize=10, weight="bold")
    labelled = set()
    for c in enc.parts:
        if c["type"] in ("led", "button") and c["type"] not in labelled:
            labelled.add(c["type"])
            q = enc.w(c["x"], c["y"])
            label = ("light pipe Ø%g" % p.lp_d if c["type"] == "led" else
                     "flexure button" if p.button == "flex" else "button cap")
            note(ax_top, (q.X, q.Y - 1.5), (q.X + (0 if c["type"] == "led" else 4), q.Y - 12),
                 label)
    ax_top.set_xlim(-ox - 6, ox + 12)
    ax_top.set_ylim(-oy - 11, oy + 6)

    # front view (from -y)
    draw_view(ax_front, asm, (0, -500, zf), (0, 0, 1), (0, 0, zf))
    ax_front.set_title("Front view", fontsize=11)
    dim(ax_front, (-ox, -zf), (ox, -zf), -4, f"{enc.out_x:.1f}")
    dim(ax_front, (ox, -zf), (ox, T - zf), 4, f"{T:.1f}", vertical=True)
    dim(ax_front, (-ox, -zf), (-ox, H - zf), -4, f"{H:.1f}", vertical=True)
    ax_front.set_xlim(-ox - 8, ox + 8)
    ax_front.set_ylim(-zf - 9, T - zf + 4)

    # left view (from -x): image x points to -y
    draw_view(ax_left, asm, (-500, 0, zf), (0, 0, 1), (0, 0, zf))
    ax_left.set_title("Left view", fontsize=11)
    left = [c for c in enc.parts if c["type"] in CONNECTORS and c["side"] == "left"]
    if left:
        c = left[0]
        spec = CONNECTORS[c["type"]]
        zc = enc.pcb_top + c["z"] + spec["zc"]
        yc = enc.w(0, c["pos"]).Y
        dim(ax_left, (oy, -zf), (oy, zc - zf), 4, f"{zc:.2f}", vertical=True)
        ow = spec["opening"][1] + 2 * p.cut_clear
        oh = spec["opening"][2] + 2 * p.cut_clear
        text = f"{c['type']} opening {ow:.2f} x {oh:.2f} (+{p.cut_clear:g} per side)"
        if "_recess" in c:
            mw, mh = spec["overmold"]
            text += (f"\nplug recess {mw + 2 * p.cut_clear:.1f} x {mh + 2 * p.cut_clear:.1f}, "
                     f"depth {c['_recess'][0]:.2f}")
        note(ax_left, (-yc, zc - zf - 1.2), (-yc - 10, -zf - 9), text)
    ax_left.set_xlim(-oy - 6, oy + 8)
    ax_left.set_ylim(-zf - 16, T - zf + 4)

    # section A-A and detail B
    items = [(base, "#d9c4b0", "////"), (lid, "#e9e1d3", "////"), (pcb, "#2e7d4f", None)]
    draw_section(ax_sec, items, x0)
    ax_sec.set_xlim(-oy - 3, oy + 3)
    ax_sec.set_ylim(-2, T + 3)
    yw = -enc.in_y / 2
    ax_sec.add_patch(plt.Rectangle((yw - p.wall - 1.5, enc.win_z[0] - 2.5), 10.5,
                                   T - enc.win_z[0] + 4, fill=False, ls="--", lw=0.7, color=MARK))
    ax_sec.text(yw - p.wall - 1.5, T + 2.0, "B", color=MARK, fontsize=10, weight="bold")

    draw_section(ax_det, items, x0)
    ax_det.set_title("Detail B (mm)", fontsize=11)
    zt = H - enc.hook_len
    zr = zt + enc.lead_h + p.hook_land + p.hook_d
    zo = p.floor + p.standoff_h
    xt, xt2 = yw + 5.5, yw + 9.0
    eps = hook_numbers(enc)["strain"] * 100
    notes = [
        ((yw - p.fit / 2, H - 2.2), (xt, H - 1.4), f"fit {p.fit:g} (lid lip and hook to wall)"),
        ((yw - p.fit - p.hook_t / 2, H - 5.0), (xt, H - 4.0),
         f"hook L {enc.hook_L:.1f}, t {p.hook_t:g}, w {p.hook_w:g}\n"
         f"strain {eps:.2f} % (PETG limit {PETG['strain_allow'] * 100:.1f} %)"),
        ((yw - 0.2, zr - 0.15), (xt, zr + 1.0),
         f"retention face {p.hook_ret_deg:.0f}°, play {p.hook_play:g}"),
        ((yw - enc.hook_y + 0.1, zr - 1.2), (xt, zr - 1.0),
         f"barb {p.hook_d:g}: overlap = deflection {enc.hook_y:.2f}"),
        ((yw - p.fit - 0.15, zt + 0.5), (xt, zt - 0.6), f"lead-in {p.hook_lead_deg:.0f}°"),
        ((yw + enc.gap["front"] / 2, enc.pcb_top - 0.8), (xt2, zo - 1.2),
         f"board gap {enc.gap['front']:.2f}"),
    ]
    cut_holes = [h for h in p.holes if abs(enc.w(*h).X - x0) < enc.ins["boss"] / 2
                 and enc.w(*h).Y < 0]
    if cut_holes:
        hy = enc.w(*cut_holes[0]).Y
        notes.append(((hy, zo - enc.ins["depth"] / 2), (xt2, zo - 3.4),
                      f"heat-set insert {p.screw}\nhole Ø{enc.ins['hole']:g} x "
                      f"{enc.ins['depth']:g}"))
    ax_sec.set_title("Section A-A (snap hook and boss)" if cut_holes else
                     "Section A-A (snap hook)", fontsize=11)
    for xy, txy, t in notes:
        note(ax_det, xy, txy, t)
    dim(ax_det, (yw - p.wall, p.floor), (yw - p.wall, zo), -3.2, f"{p.standoff_h:g}",
        vertical=True)
    dim(ax_det, (yw - p.wall, 0), (yw - p.wall, p.floor), -3.2, f"{p.floor:g}", vertical=True)
    dim(ax_det, (yw - p.wall, H), (yw - p.wall, T), -3.2, f"{p.lid_t:g}", vertical=True)
    dim(ax_det, (yw - p.wall, -0.3), (yw, -0.3), -1.0, f"{p.wall:g}")
    ax_det.set_xlim(yw - p.wall - 5.0, yw + 21.0)
    ax_det.set_ylim(-3.0, T + 1.5)

    fig.suptitle(f"{p.title or p.name}  |  outside {enc.out_x:.1f} x {enc.out_y:.1f} x "
                 f"{T:.1f} mm  |  PETG, all dimensions in mm", fontsize=13)
    fig.text(0.03, 0.015, "Generated by pcb-enclosure-generator (build123d).", fontsize=8,
             color="#666")
    fig.savefig(png_path, dpi=110)
    if pdf_path:
        fig.savefig(pdf_path)
    plt.close(fig)
