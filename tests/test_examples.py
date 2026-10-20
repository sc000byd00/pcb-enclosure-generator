"""The three examples build, pass every check and keep their outside dimensions."""

import struct
from collections import Counter

import pytest

from enclosure import build, params_from_dict
from enclosure.checks import passed, run
from enclosure.export import write_parts

OUTSIDE = {"s": (55.4, 39.0, 17.1), "m": (75.4, 55.0, 24.1), "l": (105.4, 75.0, 27.1)}


@pytest.fixture(scope="module", params=["s", "m", "l"])
def built(request):
    from conftest import EXAMPLES
    import yaml
    data = yaml.safe_load((EXAMPLES / f"{request.param}.yaml").read_text(encoding="utf-8"))
    p = params_from_dict(data)
    return p, build(p)


def test_all_checks_pass(built):
    p, (enc, parts, pcb, bodies, env) = built
    res = run(enc, parts, pcb, bodies, env, overhang=False)
    failed = [c.message for c in res if c.ok is False]
    assert passed(res), failed


def test_outside_dimensions(built):
    p, (enc, *_) = built
    got = (enc.out_x, enc.out_y, enc.H + p.lid_t)
    assert got == pytest.approx(OUTSIDE[p.name], abs=0.05)


def read_stl(path):
    data = path.read_bytes()
    n = struct.unpack_from("<I", data, 80)[0]
    tris = []
    for i in range(n):
        v = struct.unpack_from("<12f", data, 84 + i * 50)
        tris.append([tuple(round(x, 4) for x in v[3 + 3 * k:6 + 3 * k]) for k in range(3)])
    return tris


def test_exported_stl_is_watertight(built, tmp_path):
    p, (enc, parts, *_) = built
    write_parts(parts, tmp_path, formats=("stl",))
    for name in parts:
        edges = Counter()
        for a, b, c in read_stl(tmp_path / f"{name}.stl"):
            for e in ((a, b), (b, c), (c, a)):
                edges[tuple(sorted(e))] += 1
        open_edges = sum(1 for k in edges.values() if k != 2)
        assert open_edges == 0, f"{p.name}/{name}: {open_edges} non-manifold edges"


def test_parts_are_valid_solids(built):
    _, (_, parts, *_) = built
    for name, s in parts.items():
        assert s.is_valid, name
        assert s.volume > 10, name
