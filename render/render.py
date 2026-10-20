"""Render images with Blender (headless).

First write the meshes:
  enclosure build examples/*.yaml -o out --render-meshes
Then, from the repository root:
  blender -b --factory-startup -P render/render.py -- MODE OUTPUT.png [NAME]

MODE: assembled, exploded, section (cut through a snap hook and boss), variants (s, m, l
side by side). NAME is the board name for the first three modes (default m).
SAMPLES=64 in the environment renders faster.
"""

import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
mode, out_path = args[0], os.path.abspath(args[1])
name = args[2] if len(args) > 2 else "m"
root = Path.cwd() / "out" / "render"
MM = 0.001

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def material(name, rgb, rough=0.5, metal=0.0, transmission=0.0, emit=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    key = "Transmission Weight" if "Transmission Weight" in b.inputs else "Transmission"
    b.inputs[key].default_value = transmission
    if emit is not None:
        ek = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[ek].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


MATS = {
    "base": material("Base", (0.045, 0.05, 0.06), rough=0.55),
    "lid": material("Lid", (0.78, 0.79, 0.8), rough=0.5),
    "button-cap": material("Cap", (0.78, 0.79, 0.8), rough=0.5),
    "light-pipe": material("LightPipe", (0.85, 0.95, 0.9), rough=0.25, transmission=0.6,
                           emit=(0.2, 1.0, 0.55), strength=3.0),
    "board": material("Board", (0.03, 0.22, 0.1), rough=0.45),
    "components-metal": material("Metal", (0.75, 0.75, 0.76), rough=0.3, metal=1.0),
    "components-black": material("Black", (0.02, 0.02, 0.02), rough=0.4),
    "components-led": material("LED", (0.9, 0.9, 0.9), rough=0.3, emit=(0.2, 1.0, 0.55),
                               strength=5.0),
}
CUT = {  # cut faces in a lighter colour
    "base": material("CutBase", (0.55, 0.2, 0.08), rough=0.7),
    "lid": material("CutLid", (0.95, 0.62, 0.3), rough=0.7),
    "board": material("CutBoard", (0.1, 0.5, 0.25), rough=0.7),
}


def mat_for(stem):
    for k in MATS:
        if stem.startswith(k):
            return k
    return "lid"


def import_stl(path):
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.stl_import(filepath=str(path))
    except AttributeError:
        bpy.ops.import_mesh.stl(filepath=str(path))
    obj = next(o for o in bpy.data.objects if o not in before)
    obj.scale = (MM, MM, MM)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    return obj


def load(folder, dx=0.0, explode=None, cut_x=None):
    objs = []
    for path in sorted(folder.glob("*.stl")):
        obj = import_stl(path)
        key = mat_for(path.stem)
        obj.data.materials.append(MATS[key])
        if cut_x is not None and key in CUT:
            obj.data.materials.append(CUT[key])
            for poly in obj.data.polygons:
                c = poly.center
                if poly.normal.x < -0.999 and abs(c.x * MM - cut_x) < 2e-5:
                    poly.material_index = 1
        if explode:
            obj.location.z += explode.get(key.split("-")[0], explode.get(key, 0.0))
        obj.location.x += dx
        objs.append(obj)
    return objs


def bounds(objs):
    bpy.context.view_layer.update()
    cs = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
    hi = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
    return lo, hi


def stage(objs, view_dir, fill=0.78, lens=60, target=None, radius=None):
    lo, hi = bounds(objs)
    center = target if target is not None else (lo + hi) / 2
    r = radius if radius is not None else (hi - lo).length / 2
    bpy.ops.mesh.primitive_plane_add(size=4, location=(center.x, center.y, lo.z))
    bpy.context.active_object.data.materials.append(
        material("Table", (0.74, 0.75, 0.77), rough=0.9))
    s = max(r * 4, 0.12)
    for off, energy, size in [((-0.9, -1.2, 1.6), 2.2, 0.9), ((1.4, -0.4, 0.9), 0.8, 0.9),
                              ((0.2, 1.4, 1.2), 0.7, 0.8)]:
        bpy.ops.object.light_add(type="AREA", location=center + Vector(off) * s)
        light = bpy.context.active_object
        light.data.energy = energy * (s / 0.25) ** 2
        light.data.size = size * s
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.18
    scene.world = world
    bpy.ops.object.camera_add()
    cam = bpy.context.active_object
    cam.data.lens = lens
    cam.data.sensor_width = 36
    d = Vector(view_dir).normalized()
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    rot = cam.rotation_euler.to_matrix()
    right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    tx = 18 / lens * fill  # half of the 36 mm sensor width
    ty = tx * 0.75
    if radius is None:  # distance so that all corners fit
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y)
                   for z in (lo.z, hi.z)]
        dist = max(max(abs(v.dot(right)) / tx, abs(v.dot(up)) / ty) + v.dot(d)
                   for v in (c - center for c in corners))
    else:
        dist = r / ty
    cam.location = center + d * dist
    cam.data.clip_start = 0.005
    cam.data.clip_end = 10
    scene.camera = cam


def render():
    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(os.environ.get("SAMPLES", "128"))
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Filmic"
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)


if mode == "assembled":
    objs = load(root / name)
    stage(objs, (-1.15, -1.05, 0.95), fill=0.9)
elif mode == "exploded":
    objs0 = load(root / name)
    lo, hi = bounds(objs0)
    h = hi.z - lo.z
    for o in objs0:
        bpy.data.objects.remove(o)
    ex = {"board": 1.3 * h, "components": 1.3 * h, "lid": 2.9 * h,
          "light": 3.7 * h, "button": 3.7 * h}
    objs = load(root / name, explode=ex)
    stage(objs, (-1.0, -1.3, 0.85), fill=0.92)
elif mode == "section":
    import json
    cut_x = json.loads((root / f"{name}-section" / "section.json").read_text())["x"] * MM
    objs = load(root / f"{name}-section", cut_x=cut_x)
    lo, hi = bounds(objs)
    target = Vector((cut_x, lo.y + (hi.y - lo.y) * 0.2, (lo.z + hi.z) * 0.48))
    stage(objs, (-1.0, -0.22, 0.22), fill=1.0, target=target, radius=(hi.z - lo.z) * 0.62)
elif mode == "variants":
    objs = []
    x = 0.0
    for name in ("s", "m", "l"):
        part = load(root / name)
        if name == "l":  # back with DC jack and terminal towards the camera
            for o in part:
                o.rotation_euler.z = math.pi
        lo, hi = bounds(part)
        for o in part:
            o.location.x += x - lo.x
        objs += part
        # letter flat on the table in front of the enclosure
        bpy.ops.object.text_add(location=(x + (hi.x - lo.x) / 2, lo.y - 0.012, lo.z + 0.0002))
        txt = bpy.context.active_object
        txt.data.body = name.upper()
        txt.data.size = 0.011
        txt.data.align_x = "CENTER"
        txt.data.materials.append(material("Label", (0.15, 0.15, 0.16), rough=0.6))
        x += (hi.x - lo.x) + 0.018
    stage(objs, (-0.45, -1.35, 0.95), fill=1.02, lens=70)
render()
