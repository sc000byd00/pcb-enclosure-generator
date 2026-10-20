"""Command line: enclosure build BOARD.yaml [...] -o OUT"""

import argparse
import sys
from pathlib import Path

from . import checks as checks_mod
from .config import ConfigError, load
from .export import param_table, write_parts, write_render_meshes, write_report, \
    write_section_meshes
from .geometry import build


def cmd_build(args):
    out_root = Path(args.out)
    encs = []
    all_ok = True
    for path in args.boards:
        try:
            p = load(path)
        except ConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        enc, parts, pcb, bodies, env = build(p)
        res = checks_mod.run(enc, parts, pcb, bodies, env, overhang=not args.fast)
        out = out_root / p.name
        formats = [f.strip() for f in args.formats.split(",") if f.strip()]
        write_parts(parts, out, formats)
        write_report(enc, res, out)
        if args.render_meshes:
            write_render_meshes(parts, pcb, bodies, out_root / "render" / p.name)
            write_section_meshes(enc, parts, pcb, bodies, out_root / "render" / f"{p.name}-section")
        if args.drawing:
            from .drawing import draw
            draw(p, out / "drawing.png", out / "drawing.pdf",
                 built=(enc, parts, pcb, bodies, env))
        ox, oy, oz = (round(v, 1) for v in (enc.out_x, enc.out_y, enc.H + p.lid_t))
        print(f"\n{p.name}: {p.title}  outside {ox} x {oy} x {oz} mm  -> {out}")
        for n in enc.notes:
            print(f"  note  {n}")
        for c in res:
            print(f"  {c.line()}")
        all_ok &= checks_mod.passed(res)
        encs.append(enc)
    if len(encs) > 1:
        (out_root / "parameters.md").write_text(
            "# Parameters\n\nGenerated file, do not edit.\n\n" + param_table(encs) + "\n",
            encoding="utf-8")
    print("\nall checks passed" if all_ok else "\nSOME CHECKS FAILED")
    return 0 if all_ok else 1


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="enclosure",
                                 description="Parametric 3D-printable enclosures for PCBs.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build enclosures from board files")
    b.add_argument("boards", nargs="+", help="board YAML file(s)")
    b.add_argument("-o", "--out", default="out", help="output folder (default: out)")
    b.add_argument("--formats", default="step,stl,3mf",
                   help="comma-separated: step, stl, 3mf (default: all)")
    b.add_argument("--drawing", action="store_true", help="also write a dimensioned drawing")
    b.add_argument("--render-meshes", action="store_true",
                   help="also write assembly meshes for render/render.py")
    b.add_argument("--fast", action="store_true", help="skip the overhang analysis")
    b.set_defaults(func=cmd_build)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
