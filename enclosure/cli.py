"""Command line.

    enclosure build BOARD.yaml [...] -o OUT
    enclosure from-kicad BOARD.kicad_pcb [--overrides FILE] -o OUT
"""

import argparse
import sys
from pathlib import Path

import yaml

from . import checks as checks_mod
from .config import ConfigError, load, params_from_dict
from .export import param_table, write_parts, write_render_meshes, write_report, \
    write_section_meshes
from .geometry import build


def build_one(p, args, out_root):
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
        draw(p, out / "drawing.png", out / "drawing.pdf", built=(enc, parts, pcb, bodies, env))
    ox, oy, oz = (round(v, 1) for v in (enc.out_x, enc.out_y, enc.H + p.lid_t))
    print(f"\n{p.name}: {p.title}  outside {ox} x {oy} x {oz} mm  -> {out}")
    for n in enc.notes:
        print(f"  note  {n}")
    for c in res:
        print(f"  {c.line()}")
    return checks_mod.passed(res), enc


def finish(all_ok, encs, out_root):
    if len(encs) > 1:
        (out_root / "parameters.md").write_text(
            "# Parameters\n\nGenerated file, do not edit.\n\n" + param_table(encs) + "\n",
            encoding="utf-8")
    print("\nall checks passed" if all_ok else "\nSOME CHECKS FAILED")
    return 0 if all_ok else 1


def cmd_build(args):
    out_root = Path(args.out)
    encs, all_ok = [], True
    for path in args.boards:
        try:
            p = load(path)
        except ConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        ok, enc = build_one(p, args, out_root)
        all_ok &= ok
        encs.append(enc)
    return finish(all_ok, encs, out_root)


def cmd_from_kicad(args):
    from .kicad import KicadError, apply_overrides, auto_layout, read_board

    out_root = Path(args.out)
    pcb_path = Path(args.board)
    ov_path = Path(args.overrides) if args.overrides else \
        pcb_path.with_name(pcb_path.stem + ".overrides.yaml")
    try:
        data, warnings, _ = read_board(pcb_path, name=args.name)
        if ov_path.exists():
            apply_overrides(data, yaml.safe_load(ov_path.read_text(encoding="utf-8")))
        elif args.overrides:
            raise KicadError(f"overrides file not found: {ov_path}")
        auto_layout(data)
        p = params_from_dict(data, default_name=pcb_path.stem)
    except (KicadError, ConfigError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = out_root / p.name
    out.mkdir(parents=True, exist_ok=True)
    head = [f"# Generated from {pcb_path.name}"
            + (f" with {ov_path.name}" if ov_path.exists() else "") + ". Review, then",
            "# adjust the overrides file rather than this one."]
    head += [f"# warning: {w}" for w in warnings]
    (out / "board.yaml").write_text("\n".join(head) + "\n" + yaml.safe_dump(
        data, sort_keys=False, default_flow_style=None, width=100), encoding="utf-8")
    print(f"read {pcb_path.name}: {len(p.parts)} components, {len(p.holes)} holes"
          + (f", overrides {ov_path.name}" if ov_path.exists() else ""))
    for w in warnings:
        print(f"  warning  {w}")
    ok, enc = build_one(p, args, out_root)
    return finish(ok, [enc], out_root)


def _output_args(sp):
    sp.add_argument("-o", "--out", default="out", help="output folder (default: out)")
    sp.add_argument("--formats", default="step,stl,3mf",
                    help="comma-separated: step, stl, 3mf (default: all)")
    sp.add_argument("--drawing", action="store_true", help="also write a dimensioned drawing")
    sp.add_argument("--render-meshes", action="store_true",
                    help="also write assembly meshes for render/render.py")
    sp.add_argument("--fast", action="store_true", help="skip the overhang analysis")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="enclosure",
                                 description="Parametric 3D-printable enclosures for PCBs.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build enclosures from board files")
    b.add_argument("boards", nargs="+", help="board YAML file(s)")
    _output_args(b)
    b.set_defaults(func=cmd_build)
    k = sub.add_parser("from-kicad", help="build an enclosure from a KiCad board")
    k.add_argument("board", help=".kicad_pcb file")
    k.add_argument("--overrides", help="YAML with corrections and additions (default: "
                                       "BOARD.overrides.yaml next to the board, if present)")
    k.add_argument("--name", help="output name (default: board file name)")
    _output_args(k)
    k.set_defaults(func=cmd_from_kicad)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
