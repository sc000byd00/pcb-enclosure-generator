"""Figure for the README: the KiCad board as read (left) next to the rendered enclosure.

    enclosure from-kicad examples/kicad/esp32-node.kicad_pcb -o out --render-meshes
    blender -b --factory-startup -P render/render.py -- exploded out/esp32-node-render.png esp32-node
    python render/kicad_figure.py examples/kicad/esp32-node.kicad_pcb out/esp32-node-render.png \
        docs/images/from-kicad.png
"""

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402

from enclosure.kicad import read_board  # noqa: E402

COLORS = {"usb-c": "#c0392b", "barrel": "#c0392b", "terminal": "#c0392b", "module": "#1f3f8f",
          "header": "#555555", "cap": "#7d3c98", "led": "#27ae60", "button": "#d68910"}


def main(pcb, render_png, out_png):
    data, _, fps = read_board(pcb)
    types = {c["ref"]: c["type"] for c in data["components"]}
    px, py = data["board"]["size"]
    r = data["board"]["corner_radius"]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 5.6), gridspec_kw=dict(width_ratios=[1, 1.15]))
    ax.add_patch(FancyBboxPatch((0, 0), px, py, boxstyle=f"round,pad=0,rounding_size={r}",
                                facecolor="#2e7d4f", edgecolor="#1b4d30", lw=1.2))
    for f in fps:
        x0, y0, x1, y1 = f["box"]
        if f["kind"] == "hole":
            ax.add_patch(Circle(f["at"], 1.6, facecolor="white", edgecolor="#1b4d30"))
            continue
        if f["kind"] == "ignore":
            color, alpha = "#cfd8cf", 0.9
        else:
            color, alpha = COLORS.get(f["kind"], "#b7950b"), 0.85
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=color, alpha=alpha,
                               edgecolor="white", lw=0.6))
        if f["kind"] != "ignore":
            label = f"{f['ref']}\n{types.get(f['ref'], f['kind'])}"
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, label, ha="center", va="center", fontsize=7.5,
                    color="white", weight="bold")
    ax.set_xlim(-4, px + 4)
    ax.set_ylim(-4, py + 4)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{pcb.split('/')[-1]}: as read from KiCad", fontsize=11)
    ax2.imshow(mpimg.imread(render_png))
    ax2.axis("off")
    ax2.set_title("generated enclosure", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_png, dpi=110)


if __name__ == "__main__":
    main(*sys.argv[1:4])
