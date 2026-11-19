"""Fahad's bedroom, modelled from the walk-through video, rendered with Cycles.

Usage:  python room.py <layer> <out.jpg> [width] [samples]
  layer = base | l0 | l1 | l2 | l3
    base : the room with all LED strips off (soft evening light from the window)
    l0   : only Ceiling 1 (cove along left + window wall)
    l1   : only Ceiling 2 (cove along right + front wall)
    l2   : only the bed under-glow
    l3   : only the strip under the desk shelf
The light layers are rendered in white on black; the panel adds them on top of
the base with additive blending and tints them to each light's real colour.
"""
import sys, math
import bpy
from mathutils import Vector

layer = sys.argv[1] if len(sys.argv) > 1 else "base"
out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/room.jpg"
W = int(sys.argv[3]) if len(sys.argv) > 3 else 1600
SAMPLES = int(sys.argv[4]) if len(sys.argv) > 4 else 96

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---------------------------------------------------------------- materials
def mat(name, color, rough=0.5, emit=None, strength=0.0, metal=0.0, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in b.inputs: b.inputs["Specular IOR Level"].default_value = spec
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m

def tile_floor():
    m = bpy.data.materials.new("floor"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Color1"].default_value = (0.50, 0.45, 0.37, 1)
    br.inputs["Color2"].default_value = (0.53, 0.48, 0.40, 1)
    br.inputs["Mortar"].default_value = (0.42, 0.38, 0.32, 1)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.004
    br.inputs["Brick Width"].default_value = 0.6
    br.inputs["Row Height"].default_value = 0.6
    br.offset = 0.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.28
    return m

def oak():
    m = bpy.data.materials.new("oak"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    n = nt.nodes.new("ShaderNodeTexNoise"); n.inputs["Scale"].default_value = 6
    if "Detail" in n.inputs: n.inputs["Detail"].default_value = 8
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1, 18, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.50, 0.33, 0.17, 1)
    ramp.color_ramp.elements[1].color = (0.70, 0.52, 0.32, 1)
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.45
    return m

WHITE = mat("white", (0.82, 0.82, 0.80), 0.7)
CEIL = mat("ceiling", (0.85, 0.85, 0.84), 0.85)
FLOOR = tile_floor()
OAK = oak()
BLACK = mat("black", (0.015, 0.015, 0.015), 0.35)
GLOSSBLACK = mat("glossblack", (0.01, 0.01, 0.01), 0.12)
FABRIC = mat("fabric", (0.055, 0.058, 0.06), 0.9, spec=0.2)
SHEET = mat("sheet", (0.78, 0.78, 0.80), 0.9, spec=0.3)
MESH = mat("chairmesh", (0.20, 0.21, 0.22), 0.8)
METAL = mat("metal", (0.6, 0.6, 0.62), 0.3, metal=1.0)
WARDROBE = mat("wardrobe", (0.84, 0.84, 0.83), 0.4)
GLASS_SKY = mat("sky", (0.0, 0.0, 0.0), 1.0, emit=(0.32, 0.42, 0.62), strength=0.0)
SCREEN = mat("screen", (0.01, 0.01, 0.012), 0.08)
STRIP = mat("strip", (1, 1, 1), 0.5, emit=(1.0, 0.96, 0.9), strength=0.0)
ACLED = mat("acled", (0, 0, 0), 0.5, emit=(0.3, 1.0, 0.5), strength=0.0)

# ---------------------------------------------------------------- helpers
def box(name, x0, x1, y0, y1, z0, z1, m, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object; o.name = name
    o.scale = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(m)
    if bevel:
        mod = o.modifiers.new("bev", "BEVEL"); mod.width = bevel; mod.segments = 3
    return o

def cyl(name, x, y, z0, z1, r, m, verts=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=z1 - z0, location=(x, y, (z0 + z1) / 2))
    o = bpy.context.object; o.name = name; o.data.materials.append(m); return o

LIGHTS = {}
def strip_light(key, center, size_x, size_y, rot, power, glow=None):
    """A thin area light (the LED strip) plus an emissive mesh so the strip itself is visible."""
    ld = bpy.data.lights.new(f"{key}_{len(LIGHTS.get(key, []))}", "AREA")
    ld.shape = "RECTANGLE"; ld.size = size_x; ld.size_y = size_y
    ld.energy = power; ld.color = (1.0, 0.96, 0.9)
    if hasattr(ld, "spread"): ld.spread = math.radians(150)
    o = bpy.data.objects.new(ld.name, ld); o.location = center; o.rotation_euler = rot
    scene.collection.objects.link(o)
    LIGHTS.setdefault(key, []).append(o)
    if glow:
        g = box(f"{key}_glow{len(LIGHTS[key])}", *glow, STRIP.copy())
        LIGHTS.setdefault(key + "_mesh", []).append(g)
    return o

# ---------------------------------------------------------------- room shell
RX, RY, RZ = 4.0, 4.0, 3.0          # x: left→right, y: front→window wall, z: up
FC = 2.80                           # false ceiling height
GAP = 0.16                          # cove slot width along the walls
box("floor", -0.1, RX + 0.1, -0.1, RY + 0.1, -0.05, 0, FLOOR)
box("ceiling", -0.1, RX + 0.1, -0.1, RY + 0.1, RZ, RZ + 0.05, CEIL)
box("falseceil", GAP, RX - GAP, GAP, RY - GAP, FC - 0.08, FC, CEIL)
box("wall_left", -0.1, 0, -0.1, RY + 0.1, 0, RZ, WHITE)
box("wall_right", RX, RX + 0.1, -0.1, RY + 0.1, 0, RZ, WHITE)
box("wall_front", -0.1, RX + 0.1, -0.1, 0, 0, RZ, WHITE)
# window wall with an opening
WX0, WX1, WZ0, WZ1 = 0.95, 2.55, 1.0, 2.2
box("ww_l", -0.1, WX0, RY, RY + 0.25, 0, RZ, WHITE)
box("ww_r", WX1, RX + 0.1, RY, RY + 0.25, 0, RZ, WHITE)
box("ww_b", WX0, WX1, RY, RY + 0.25, 0, WZ0, WHITE)
box("ww_t", WX0, WX1, RY, RY + 0.25, WZ1, RZ, WHITE)
# skirting
for nm, a in [("sk_l", (0, 0.012, 0, RY, 0, 0.08)), ("sk_r", (RX - 0.012, RX, 0, RY, 0, 0.08)), ("sk_b", (0, RX, RY - 0.012, RY, 0, 0.08))]:
    box(nm, *a, WHITE)

# window: black frame + grill + dusky sky behind
box("sky", WX0 - 0.2, WX1 + 0.2, RY + 0.6, RY + 0.62, WZ0 - 0.3, WZ1 + 0.3, GLASS_SKY)
for nm, a in [("wf_l", (WX0, WX0 + 0.06, RY + 0.05, RY + 0.1, WZ0, WZ1)), ("wf_r", (WX1 - 0.06, WX1, RY + 0.05, RY + 0.1, WZ0, WZ1)),
              ("wf_b", (WX0, WX1, RY + 0.05, RY + 0.1, WZ0, WZ0 + 0.06)), ("wf_t", (WX0, WX1, RY + 0.05, RY + 0.1, WZ1 - 0.06, WZ1)),
              ("wf_m", (WX0, WX1, RY + 0.05, RY + 0.1, 1.58, 1.62))]:
    box(nm, *a, BLACK)
for i in range(1, 4):
    x = WX0 + (WX1 - WX0) * i / 4
    box(f"wf_v{i}", x - 0.03, x + 0.03, RY + 0.05, RY + 0.1, WZ0, WZ1, BLACK)
for i in range(1, 12):  # thin grill bars
    x = WX0 + (WX1 - WX0) * i / 12
    box(f"grill_v{i}", x - 0.006, x + 0.006, RY + 0.02, RY + 0.03, WZ0, WZ1, BLACK)
for z in (1.3, 1.9):
    box(f"grill_h{z}", WX0, WX1, RY + 0.02, RY + 0.03, z - 0.006, z + 0.006, BLACK)

# AC unit above the window
ac = box("ac", 1.25, 2.25, RY - 0.22, RY, 2.42, 2.72, WHITE, bevel=0.03)
box("ac_vent", 1.3, 2.2, RY - 0.225, RY - 0.2, 2.45, 2.47, BLACK)
box("ac_led", 2.12, 2.14, RY - 0.225, RY - 0.22, 2.60, 2.62, ACLED)

# wardrobe along the left wall (white, tall doors + overhead cabinets, black bar handles)
WD = 0.55
box("wardrobe", 0, WD, 0.55, 3.15, 0.0, 2.2, WARDROBE)
box("overhead", 0, WD, 0.55, 3.15, 2.22, FC - 0.08, WARDROBE)
for i in range(1, 6):
    y = 0.55 + 2.6 * i / 6
    box(f"wd_gap{i}", WD, WD + 0.003, y - 0.003, y + 0.003, 0.02, 2.2, BLACK)
for i in range(6):
    y = 0.55 + 2.6 * (i + 0.5) / 6 + (0.12 if i % 2 == 0 else -0.12)
    box(f"wd_h{i}", WD, WD + 0.025, y - 0.008, y + 0.008, 0.85, 1.45, BLACK)
    box(f"oh_h{i}", WD, WD + 0.025, y - 0.008, y + 0.008, 2.26, 2.36, BLACK)

# bed: dark grey base raised off the floor, channel-tufted headboard, white sheets
BX0, BX1, BY0, BY1 = 1.0, 2.5, 1.55, RY - 0.08
box("bed_base", BX0, BX1, BY0, BY1, 0.10, 0.36, FABRIC, bevel=0.02)
box("bed_plinth", BX0 + 0.25, BX1 - 0.25, BY0 + 0.25, BY1 - 0.25, 0.0, 0.10, BLACK)
box("mattress", BX0 + 0.03, BX1 - 0.03, BY0 + 0.03, BY1 - 0.05, 0.36, 0.58, SHEET, bevel=0.05)
box("headboard", BX0 - 0.05, BX1 + 0.05, RY - 0.1, RY - 0.02, 0.36, 1.12, FABRIC, bevel=0.02)
for i in range(1, 12):
    x = BX0 - 0.05 + (BX1 - BX0 + 0.1) * i / 12
    box(f"hb_ch{i}", x - 0.004, x + 0.004, RY - 0.104, RY - 0.1, 0.4, 1.08, BLACK)
box("pillow1", BX0 + 0.12, BX0 + 0.68, RY - 0.48, RY - 0.12, 0.58, 0.72, SHEET, bevel=0.06)
box("pillow2", BX1 - 0.68, BX1 - 0.12, RY - 0.48, RY - 0.12, 0.58, 0.72, SHEET, bevel=0.06)
box("duvet", BX0 + 0.02, BX1 - 0.02, BY0 + 0.02, BY0 + 1.3, 0.58, 0.63, SHEET, bevel=0.04)

# desk along the right wall: oak top, black T-frame legs, monitor, chair
DX0, DY0, DY1, DH = RX - 0.72, 0.65, 2.25, 0.75
box("desk_top", DX0, RX - 0.02, DY0, DY1, DH - 0.03, DH, OAK, bevel=0.004)
for y in (DY0 + 0.12, DY1 - 0.12):
    box(f"leg{y}", DX0 + 0.3, DX0 + 0.38, y - 0.04, y + 0.04, 0.03, DH - 0.03, BLACK)
    box(f"foot{y}", DX0 + 0.02, RX - 0.06, y - 0.035, y + 0.035, 0.0, 0.03, BLACK)
box("crossbar", DX0 + 0.32, DX0 + 0.36, DY0 + 0.12, DY1 - 0.12, DH - 0.1, DH - 0.06, BLACK)
box("monitor", RX - 0.2, RX - 0.17, 1.15, 1.75, DH + 0.12, DH + 0.47, GLOSSBLACK, bevel=0.005)
box("screen", RX - 0.201, RX - 0.2, 1.17, 1.73, DH + 0.14, DH + 0.45, SCREEN)
box("mon_stand", RX - 0.16, RX - 0.12, 1.43, 1.47, DH, DH + 0.2, BLACK)
box("mon_foot", RX - 0.24, RX - 0.08, 1.37, 1.53, DH, DH + 0.01, BLACK)
box("keyboard", DX0 + 0.12, DX0 + 0.26, 1.2, 1.62, DH, DH + 0.015, mat("kb", (0.9, 0.9, 0.9), 0.5), bevel=0.004)
box("headphones", DX0 + 0.15, DX0 + 0.3, 1.85, 2.02, DH, DH + 0.04, BLACK, bevel=0.02)
# chair (grey mesh)
CX, CY = DX0 - 0.38, 1.7
box("seat", CX - 0.24, CX + 0.24, CY - 0.24, CY + 0.24, 0.46, 0.53, MESH, bevel=0.03)
box("back", CX - 0.27, CX - 0.21, CY - 0.22, CY + 0.22, 0.58, 1.2, MESH, bevel=0.03)
box("headrest", CX - 0.27, CX - 0.21, CY - 0.13, CY + 0.13, 1.24, 1.36, MESH, bevel=0.02)
cyl("gaslift", CX, CY, 0.1, 0.46, 0.025, METAL)
for k in range(5):
    a = k * 2 * math.pi / 5 + 0.3
    sp = box(f"spoke{k}", -0.15, 0.15, -0.015, 0.015, 0.06, 0.09, BLACK)
    sp.location = (CX + 0.15 * math.cos(a), CY + 0.15 * math.sin(a), 0); sp.rotation_euler = (0, 0, a)
    cyl(f"caster{k}", CX + 0.3 * math.cos(a), CY + 0.3 * math.sin(a), 0.0, 0.05, 0.025, BLACK, 12)
box("armrest", CX - 0.2, CX + 0.15, CY - 0.27, CY - 0.23, 0.7, 0.73, BLACK)
box("armrest2", CX - 0.2, CX + 0.15, CY + 0.23, CY + 0.27, 0.7, 0.73, BLACK)

# floating oak shelf above the desk, LED strip on its underside
SZ = 2.0
box("shelf", RX - 0.22, RX, 0.55, 2.45, SZ, SZ + 0.035, OAK, bevel=0.003)
box("book", RX - 0.18, RX - 0.03, 0.62, 0.66, SZ + 0.035, SZ + 0.25, mat("book", (0.25, 0.2, 0.15), 0.6))

# small details: switch plates
for x, y, z, rot in [(RX - 0.005, 2.6, 1.2, 0), (2.85, RY - 0.005, 1.15, 1)]:
    if rot: box(f"sw{x}", x - 0.12, x + 0.12, y, y + 0.005, z - 0.05, z + 0.05, BLACK)
    else: box(f"sw{y}", x, x + 0.005, y - 0.12, y + 0.12, z - 0.05, z + 0.05, BLACK)

# ---------------------------------------------------------------- the four LED strips
down = (0, 0, 0)          # area lights face -Z by default
ZC = FC + 0.06            # strip sits in the slot, above the false-ceiling edge
P_COVE = 9              # watts per wall run
# Ceiling 1: left wall + window wall
strip_light("l0", (GAP / 2, RY / 2, ZC), 0.06, RY - 0.1, down, P_COVE)
strip_light("l0", (RX / 2, RY - GAP / 2, ZC), RX - 0.1, 0.06, down, P_COVE)
# Ceiling 2: right wall + front wall
strip_light("l1", (RX - GAP / 2, RY / 2, ZC), 0.06, RY - 0.1, down, P_COVE)
strip_light("l1", (RX / 2, GAP / 2, ZC), RX - 0.1, 0.06, down, P_COVE)
# Bed under-glow (all four sides, under the base)
z = 0.085
strip_light("l2", ((BX0 + BX1) / 2, BY0 + 0.03, z), BX1 - BX0 - 0.1, 0.03, down, 3, glow=(BX0 + 0.05, BX1 - 0.05, BY0 + 0.05, BY0 + 0.07, 0.09, 0.1))
strip_light("l2", (BX0 + 0.03, (BY0 + BY1) / 2, z), 0.03, BY1 - BY0 - 0.1, down, 3.5, glow=(BX0 + 0.05, BX0 + 0.07, BY0 + 0.05, BY1 - 0.05, 0.09, 0.1))
strip_light("l2", (BX1 - 0.03, (BY0 + BY1) / 2, z), 0.03, BY1 - BY0 - 0.1, down, 3.5, glow=(BX1 - 0.07, BX1 - 0.05, BY0 + 0.05, BY1 - 0.05, 0.09, 0.1))
# Desk shelf strip
strip_light("l3", (RX - 0.18, 1.5, SZ - 0.006), 0.012, 1.8, down, 5, glow=(RX - 0.19, RX - 0.17, 0.6, 2.4, SZ - 0.005, SZ))

# ---------------------------------------------------------------- world / camera
world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.55, 0.62, 0.78, 1)

cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 15; cam_d.sensor_width = 36
cam = bpy.data.objects.new("cam", cam_d); scene.collection.objects.link(cam); scene.camera = cam
cam.location = Vector((2.25, 0.18, 1.62))
target = Vector((2.0, RY, 1.02))
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
cam_d.shift_y = 0.0

# ---------------------------------------------------------------- which layer
def set_strength(m, v): m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = v
for key, objs in LIGHTS.items():
    on = key.split("_")[0] == layer
    for o in objs:
        if key.endswith("_mesh"):
            for ms in o.data.materials: set_strength(ms, 6.0 if on else 0.0)
        else:
            o.hide_render = not on
if layer == "base":
    bg.inputs["Strength"].default_value = 0.025       # faint ambient
    set_strength(GLASS_SKY, 0.9)                       # dusky window
    set_strength(ACLED, 0.0)
    set_strength(SCREEN, 0.0)
    # a gentle fill from the window so the room reads at night
    ld = bpy.data.lights.new("winfill", "AREA"); ld.size = WX1 - WX0; ld.size_y = WZ1 - WZ0
    ld.energy = 14; ld.color = (0.62, 0.72, 0.95)
    o = bpy.data.objects.new("winfill", ld); o.location = ((WX0 + WX1) / 2, RY + 0.12, (WZ0 + WZ1) / 2)
    o.rotation_euler = (math.radians(90), 0, 0); scene.collection.objects.link(o)
    ld2 = bpy.data.lights.new("roomfill", "AREA"); ld2.size = 2.5; ld2.energy = 4; ld2.color = (1.0, 0.95, 0.9)
    o2 = bpy.data.objects.new("roomfill", ld2); o2.location = (2.0, 1.2, FC - 0.1); scene.collection.objects.link(o2)
else:
    bg.inputs["Strength"].default_value = 0.0

# ---------------------------------------------------------------- render
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
try: scene.cycles.denoiser = "OPENIMAGEDENOISE"
except Exception: pass
scene.cycles.max_bounces = 5; scene.cycles.diffuse_bounces = 4; scene.cycles.glossy_bounces = 2
scene.cycles.transmission_bounces = 0; scene.cycles.transparent_max_bounces = 2
scene.cycles.use_adaptive_sampling = True
scene.render.resolution_x = W; scene.render.resolution_y = int(W * 3 / 4); scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "Standard"
scene.view_settings.exposure = 0.0
scene.render.image_settings.file_format = "JPEG"; scene.render.image_settings.quality = 88
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("wrote", out)
