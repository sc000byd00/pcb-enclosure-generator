"""Write the example KiCad boards (KiCad 8 format).

The footprints carry their F.Fab outline, courtyard and pads, like the KiCad standard
library footprints of the same name; copper tracks are left out, only placement matters
for the enclosure.

    python examples/kicad/make_boards.py
"""

import math
import uuid
from pathlib import Path

HERE = Path(__file__).parent
ORIGIN = (100.0, 100.0)  # board front left corner sits at (100, 100 + depth) in KiCad


def _uuid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "pcb-enclosure-generator/" + "/".join(map(str, parts))))


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def n(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


# ---------- footprint bodies (local coordinates, mm) ----------
def rect(x0, y0, x1, y1, layer, key):
    return (f'(fp_rect (start {n(x0)} {n(y0)}) (end {n(x1)} {n(y1)}) (stroke (width 0.1) '
            f'(type solid)) (fill none) (layer {q(layer)}) (uuid {q(_uuid(key, layer, x0, y0))}))')


def circle(cx, cy, r, layer, key):
    return (f'(fp_circle (center {n(cx)} {n(cy)}) (end {n(cx + r)} {n(cy)}) (stroke (width 0.1) '
            f'(type solid)) (fill none) (layer {q(layer)}) (uuid {q(_uuid(key, layer, r))}))')


def smd(num, x, y, w, h, key):
    return (f'(pad {q(num)} smd roundrect (at {n(x)} {n(y)}) (size {n(w)} {n(h)}) '
            f'(layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25) '
            f'(uuid {q(_uuid(key, "pad", num))}))')


def tht(num, x, y, d, drill, key, shape="circle"):
    return (f'(pad {q(num)} thru_hole {shape} (at {n(x)} {n(y)}) (size {n(d)} {n(d)}) '
            f'(drill {n(drill)}) (layers "*.Cu" "*.Mask") (uuid {q(_uuid(key, "pad", num))}))')


def npth(x, y, d, key):
    return (f'(pad "" np_thru_hole circle (at {n(x)} {n(y)}) (size {n(d)} {n(d)}) '
            f'(drill {n(d)}) (layers "*.Cu" "*.Mask") (uuid {q(_uuid(key, "npth", x, y))}))')


def body_box(x0, y0, x1, y1, key, margin=0.25):
    return [rect(x0, y0, x1, y1, "F.Fab", key),
            rect(x0 - margin, y0 - margin, x1 + margin, y1 + margin, "F.CrtYd", key)]


LIBRARY = {
    "MountingHole:MountingHole_2.7mm_M2.5":
        lambda k: [circle(0, 0, 2.7, "F.Fab", k), circle(0, 0, 2.95, "F.CrtYd", k),
                   npth(0, 0, 2.7, k)],
    "MountingHole:MountingHole_3.2mm_M3":
        lambda k: [circle(0, 0, 3.2, "F.Fab", k), circle(0, 0, 3.45, "F.CrtYd", k),
                   npth(0, 0, 3.2, k)],
    # receptacle opening towards -y; 8.94 wide, 7.35 deep
    "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P":
        lambda k: body_box(-4.47, -3.675, 4.47, 3.675, k)
        + [smd(str(i + 1), -2.75 + i * 0.5, 2.6, 0.3, 1.1, k) for i in range(12)]
        + [tht("S1", -4.32, -1.0, 1.0, 0.6, k), tht("S2", 4.32, -1.0, 1.0, 0.6, k)],
    # opening towards -y; 9.0 wide, 14.4 deep
    "Connector_BarrelJack:BarrelJack_Horizontal":
        lambda k: body_box(-4.5, -7.2, 4.5, 7.2, k)
        + [tht("1", 0, 6.2, 3.5, 1.8, k), tht("2", 0, 0.2, 3.5, 1.8, k),
           tht("3", 4.7, 3.2, 3.5, 1.8, k)],
    # wire entry towards -y; 10.16 wide, 7.6 deep
    "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal":
        lambda k: body_box(-5.08, -3.8, 5.08, 3.8, k)
        + [tht("1", -2.54, 1.0, 2.6, 1.3, k, "rect"), tht("2", 2.54, 1.0, 2.6, 1.3, k)],
    "LED_SMD:LED_0603_1608Metric":
        lambda k: body_box(-0.8, -0.4, 0.8, 0.4, k)
        + [smd("1", -0.7875, 0, 0.875, 0.95, k), smd("2", 0.7875, 0, 0.875, 0.95, k)],
    "Resistor_SMD:R_0603_1608Metric":
        lambda k: body_box(-0.8, -0.4, 0.8, 0.4, k)
        + [smd("1", -0.825, 0, 0.8, 0.95, k), smd("2", 0.825, 0, 0.8, 0.95, k)],
    # 6 x 6 tactile switch, pin 1 at the origin
    "Button_Switch_THT:SW_PUSH_6mm_H5mm":
        lambda k: body_box(0.25, -0.75, 6.25, 5.25, k)
        + [tht(str(i + 1), x, y, 2.0, 1.1, k) for i, (x, y) in
           enumerate([(0, 0), (6.5, 0), (0, 4.5), (6.5, 4.5)])],
    "RF_Module:ESP32-WROOM-32":
        lambda k: body_box(-9.0, -12.75, 9.0, 12.75, k)
        + [smd(str(i + 1), -8.75, -5.0 + i * 1.27, 1.5, 0.9, k) for i in range(14)],
    "Capacitor_SMD:CP_Elec_6.3x7.7":
        lambda k: body_box(-3.3, -3.3, 3.3, 3.3, k)
        + [smd("1", -2.7, 0, 3.3, 1.6, k), smd("2", 2.7, 0, 3.3, 1.6, k)],
    "Capacitor_SMD:CP_Elec_8x11.5":
        lambda k: body_box(-4.15, -4.15, 4.15, 4.15, k)
        + [smd("1", -3.25, 0, 3.5, 2.5, k), smd("2", 3.25, 0, 3.5, 2.5, k)],
    "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical":
        lambda k: body_box(-1.27, -1.27, 1.27, 19.05, k)
        + [tht(str(i + 1), 0, i * 2.54, 1.7, 1.0, k, "rect" if i == 0 else "circle")
           for i in range(8)],
    "Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering":
        lambda k: body_box(-1.25, -1.25, 1.25, 1.25, k)
        + [smd(str(i + 1), -0.975 + (i % 4) * 0.65, -0.8 if i < 4 else 0.8, 0.35, 0.5, k)
           for i in range(8)],
}


def footprint(lib_name, ref, value, x, y, rot=0.0, layer="F.Cu"):
    key = ref
    at = f"(at {n(x)} {n(y)}{' ' + n(rot) if rot else ''})"
    parts = [
        f"(footprint {q(lib_name)}",
        f"(layer {q(layer)})",
        f"(uuid {q(_uuid('fp', ref))})",
        at,
        f'(property "Reference" {q(ref)} (at 0 -3 {n(rot)}) (layer "F.SilkS") '
        f'(uuid {q(_uuid(ref, "ref"))}) (effects (font (size 1 1) (thickness 0.15))))',
        f'(property "Value" {q(value)} (at 0 3 {n(rot)}) (layer "F.Fab") '
        f'(uuid {q(_uuid(ref, "val"))}) (effects (font (size 1 1) (thickness 0.15))))',
    ]
    if lib_name.startswith("MountingHole"):
        parts.append("(attr exclude_from_pos_files exclude_from_bom)")
    elif "_THT" in lib_name or "PinHeader" in lib_name or "BarrelJack" in lib_name \
            or "TerminalBlock" in lib_name:
        parts.append("(attr through_hole)")
    else:
        parts.append("(attr smd)")
    parts += LIBRARY[lib_name](ref)
    return "\n    ".join(parts) + ")"


def outline_rounded(w, h, r):
    x0, y0 = ORIGIN
    x1, y1 = x0 + w, y0 + h
    s = 'stroke (width 0.05) (type default)'

    def line(a, b, k):
        return (f'(gr_line (start {n(a[0])} {n(a[1])}) (end {n(b[0])} {n(b[1])}) ({s}) '
                f'(layer "Edge.Cuts") (uuid {q(_uuid("edge", k))}))')

    def arc(a, m, b, k):
        return (f'(gr_arc (start {n(a[0])} {n(a[1])}) (mid {n(m[0])} {n(m[1])}) '
                f'(end {n(b[0])} {n(b[1])}) ({s}) (layer "Edge.Cuts") (uuid {q(_uuid("arc", k))}))')

    d = r * (1 - math.sqrt(0.5))
    return [
        line((x0 + r, y0), (x1 - r, y0), 1), line((x1, y0 + r), (x1, y1 - r), 2),
        line((x1 - r, y1), (x0 + r, y1), 3), line((x0, y1 - r), (x0, y0 + r), 4),
        arc((x1 - r, y0), (x1 - d, y0 + d), (x1, y0 + r), 1),
        arc((x1, y1 - r), (x1 - d, y1 - d), (x1 - r, y1), 2),
        arc((x0 + r, y1), (x0 + d, y1 - d), (x0, y1 - r), 3),
        arc((x0, y0 + r), (x0 + d, y0 + d), (x0 + r, y0), 4),
    ]


def outline_rect(w, h):
    x0, y0 = ORIGIN
    return [f'(gr_rect (start {n(x0)} {n(y0)}) (end {n(x0 + w)} {n(y0 + h)}) '
            f'(stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts") '
            f'(uuid {q(_uuid("edge", "rect"))}))']


LAYERS = """(layers
    (0 "F.Cu" signal) (31 "B.Cu" signal)
    (34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen") (38 "B.Mask" user) (39 "F.Mask" user)
    (44 "Edge.Cuts" user) (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user) (49 "F.Fab" user))"""


def board_file(title, items, thickness=1.6):
    head = (f'(kicad_pcb (version 20240108) (generator "pcb-enclosure-generator") '
            f'(generator_version "8.0")\n  (general (thickness {n(thickness)}) '
            f'(legacy_teardrops no))\n  (paper "A4")\n  (title_block (title {q(title)}))\n  '
            f'{LAYERS}\n  (setup (pad_to_mask_clearance 0))\n  (net 0 "")')
    return head + "\n  " + "\n  ".join(items) + "\n)\n"


def kc(bx, by, depth):
    """Board coordinates (front left origin, y to the back) -> KiCad coordinates."""
    return ORIGIN[0] + bx, ORIGIN[1] + depth - by


def esp32_node():
    """70 x 50, rounded corners: ESP32 module, USB-C left, LED, button, cap, header, sensor."""
    W, D = 70.0, 50.0
    P = lambda bx, by: kc(bx, by, D)  # noqa: E731
    items = outline_rounded(W, D, 1.5)
    for i, (hx, hy) in enumerate([(8, 4), (62, 4), (8, 46), (62, 46)]):
        items.append(footprint("MountingHole:MountingHole_2.7mm_M2.5", f"H{i + 1}",
                               "MountingHole", *P(hx, hy)))
    # USB-C on the left edge, opening outwards (local -y -> -x at 90°), 0.6 mm overhang
    items.append(footprint("Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P", "J1",
                           "USB_C", *P(-0.6 + 3.675, 25), 90))
    items.append(footprint("RF_Module:ESP32-WROOM-32", "U1", "ESP32-WROOM-32",
                           *P(36 + 12.75, 16 + 9.0), 90))
    items.append(footprint("Capacitor_SMD:CP_Elec_6.3x7.7", "C1", "100u", *P(20, 14)))
    # header pin 1 at the left end, row along +x (local +y -> +x at 90°)
    items.append(footprint("Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", "J2",
                           "Conn_01x08", *P(36 + 1.27, 43.25), 90))
    items.append(footprint("Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering",
                           "U2", "BME280", *P(66, 23.5)))
    items.append(footprint("LED_SMD:LED_0603_1608Metric", "D1", "LED", *P(14, 38)))
    bx, by = P(26, 38)
    items.append(footprint("Button_Switch_THT:SW_PUSH_6mm_H5mm", "SW1", "SW_Push",
                           bx - 3.25, by - 2.25))
    items.append(footprint("Resistor_SMD:R_0603_1608Metric", "R1", "1k", *P(14, 34)))
    items.append(footprint("Resistor_SMD:R_0603_1608Metric", "R2", "10k", *P(20, 44)))
    return board_file("ESP32 sensor node", items)


def gateway():
    """100 x 70, square corners, M3: DC jack and terminal at the back, USB-C left, two LEDs,
    button, module, cap, sensor."""
    W, D = 100.0, 70.0
    P = lambda bx, by: kc(bx, by, D)  # noqa: E731
    items = outline_rect(W, D)
    for i, (hx, hy) in enumerate([(5, 5), (95, 5), (5, 65), (95, 65)]):
        items.append(footprint("MountingHole:MountingHole_3.2mm_M3", f"H{i + 1}",
                               "MountingHole", *P(hx, hy)))
    # back edge is the top edge in KiCad: opening (-y local) already points there
    items.append(footprint("Connector_BarrelJack:BarrelJack_Horizontal", "J1", "DC",
                           *P(14, D - 7.2)))
    items.append(footprint(
        "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
        "J2", "Screw_Terminal", *P(32, D + 0.3 - 3.8)))
    items.append(footprint("Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P", "J3",
                           "USB_C", *P(-0.6 + 3.675, 40), 90))
    items.append(footprint("RF_Module:ESP32-WROOM-32", "U1", "ESP32-WROOM-32",
                           *P(52 + 12.75, 20 + 9.0), 90))
    items.append(footprint("Capacitor_SMD:CP_Elec_8x11.5", "C1", "470u", *P(30, 24)))
    items.append(footprint("Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering",
                           "U2", "BME280", *P(96, 40)))
    items.append(footprint("LED_SMD:LED_0603_1608Metric", "D1", "LED", *P(88, 58)))
    items.append(footprint("LED_SMD:LED_0603_1608Metric", "D2", "LED", *P(88, 50)))
    bx, by = P(88, 30)
    items.append(footprint("Button_Switch_THT:SW_PUSH_6mm_H5mm", "SW1", "SW_Push",
                           bx - 3.25, by - 2.25))
    return board_file("Gateway", items)


BOARDS = {"esp32-node": esp32_node, "gateway": gateway}


def main():
    for name, make in BOARDS.items():
        path = HERE / f"{name}.kicad_pcb"
        path.write_text(make(), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
