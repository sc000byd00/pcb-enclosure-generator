"""Material assumptions and the component library.

All dimensions in mm. Connector, switch and insert sizes are typical values;
check the datasheet of the actual part before printing.
"""

# PETG, FDM printed. Assumed values, not measured.
PETG = dict(
    E=2000.0,  # MPa, tensile modulus of printed parts
    # Allowed strain during assembly. Hooks are printed standing, so the bending
    # stress runs across the layers: keep well below the elongation at break.
    strain_allow=0.020,
    mu=0.3,  # friction PETG on PETG
)

# Connectors mounted at a board edge.
#   w, h, d   body width (along the edge), height, depth (into the board)
#   opening   shape and size of the cutout before clearance
#   zc        height of the opening centre above the board top
#   overmold  size of the mating plug's overmold, or None
#   reach     how far the plug reaches beyond the connector face
CONNECTORS = {
    "usb-c": dict(w=8.94, h=3.26, d=7.35, opening=("stadium", 8.94, 3.26), zc=1.63,
                  overmold=(12.4, 6.6), reach=1.0),
    # DC barrel jack 5.5/2.1
    "barrel": dict(w=9.0, h=11.0, d=14.4, opening=("round", 6.3, 6.3), zc=6.5,
                   overmold=None, reach=3.0),
    # 2-pole screw terminal, 5.08 mm pitch, wire entry towards the wall
    "terminal": dict(w=10.16, h=10.0, d=7.6, opening=("rect", 9.4, 4.2), zc=3.6,
                     overmold=None, reach=6.0),
}

# 6 x 6 tactile switch
SWITCH = dict(w=6.0, body_h=3.5, h=5.0, plunger_d=3.5, travel=0.25, force=1.6)

# 0603 SMD LED
LED = dict(w=1.6, d=0.8, h=0.6)

# Heat-set inserts: hole, depth, boss diameter
INSERTS = {
    "M2.5": dict(hole=3.6, depth=4.6, boss=6.2),
    "M3": dict(hole=4.0, depth=6.2, boss=7.4),
}

# Board-side normals, pointing outwards
SIDE_NAMES = ("left", "right", "front", "back")
