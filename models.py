"""Ceramic coffee pot, mug and milk jug (Blender, 1 BU = 1 cm), shared by the renderer and the CFD geometry export.

Pouring geometry (world, cm; mug inner bottom at the origin):
  coffee spout tip  P_TIP  = (-3.0, 0, 13.0), stream leaves at ~15 deg below horizontal towards +x
  milk jug lip      M_TIP  = ( 5.5, 0, 12.0), stream leaves towards -x
"""
import math, numpy as np, bpy, bmesh
from mathutils import Matrix, Vector

R_IN, R_OUT, Z_RIM, BASE = 4.0, 4.45, 8.5, 0.6
P_TIP = Vector((-4.5, 0.0, 13.0))
POT_TILT = math.radians(89)
M_TIP = Vector((5.5, 0.0, 12.0))
JUG_TILT = math.radians(55)

MUG_PROFILE = [(0.0, -BASE), (R_OUT - 0.3, -BASE), (R_OUT - 0.1, -BASE + 0.05), (R_OUT, -BASE + 0.3), (R_OUT, Z_RIM - 0.15),
               (R_OUT - 0.05, Z_RIM - 0.03), ((R_IN + R_OUT) / 2, Z_RIM), (R_IN + 0.05, Z_RIM - 0.03), (R_IN, Z_RIM - 0.15),
               (R_IN, 0.25), (R_IN - 0.1, 0.06), (R_IN - 0.3, 0.0), (0.0, 0.0)]

def lathe_mesh(name, profile, steps=128):
    """Closed surface of revolution (profile in r,z; ends on the axis) as a real mesh with outward normals."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r < 1e-9:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / steps), r * math.sin(2 * math.pi * k / steps), z)) for k in range(steps)])
    for a, b in zip(rings[:-1], rings[1:]):
        if len(a) == 1 and len(b) == 1: continue
        for k in range(steps):
            k1 = (k + 1) % steps
            if len(a) == 1:   bm.faces.new((a[0], b[k1], b[k]))
            elif len(b) == 1: bm.faces.new((a[k], a[k1], b[0]))
            else:             bm.faces.new((a[k], a[k1], b[k1], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for f in me.polygons: f.use_smooth = True
    return me

def obj(name, me, mat=None):
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    if mat: me.materials.append(mat)
    return ob

def tube(name, pts, radii, mat=None, sides=32):
    """Tube along a polyline with varying radius (closed caps)."""
    pts = [Vector(p) for p in pts]; radii = [float(r) for r in radii]
    bm = bmesh.new(); rings = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        a = Vector((0, 1, 0)) if abs(t.y) < 0.9 else Vector((1, 0, 0))
        u = t.cross(a).normalized(); v = t.cross(u)
        rings.append([bm.verts.new(p + radii[i] * (math.cos(2 * math.pi * k / sides) * u + math.sin(2 * math.pi * k / sides) * v)) for k in range(sides)])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(sides):
            bm.faces.new((a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for f in me.polygons: f.use_smooth = True
    return obj(name, me, mat)

def bezier(p0, p1, p2, p3, n=24):
    t = np.linspace(0, 1, n)[:, None]
    P = [np.array(p) for p in (p0, p1, p2, p3)]
    return ((1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t ** 2 * P[2] + t ** 3 * P[3]).tolist()

def build_mug(mat):
    mug = obj('mug', lathe_mesh('mug', MUG_PROFILE, 160), mat)
    # handle: an arc of tube on the +x side
    arc = [(R_OUT - 0.25 + 2.2 * math.sin(a), 0, 4.3 + 2.6 * math.cos(a)) for a in np.linspace(0.02 * math.pi, 0.98 * math.pi, 32)]   # ends sink into the wall
    h = tube('mug_handle', arc, [0.42] * len(arc), mat)
    h.scale = (1.0, 1.25, 1.0)
    return mug, h

# ---------------- coffee pot (local frame: base centre at origin, spout towards +x) ----------------
POT_PROFILE = [(0.0, 0.0), (4.6, 0.0), (5.2, 0.4), (5.9, 2.0), (6.3, 4.5), (6.1, 7.5), (5.3, 10.5), (4.2, 12.8),
               (3.8, 14.0), (4.0, 14.6), (3.75, 14.7), (3.6, 14.2), (0.0, 14.2)]
SPOUT = bezier((4.8, 0, 3.0), (8.0, 0, 3.4), (9.6, 0, 7.4), (12.0, 0, 10.5), 28)
SPOUT_TIP_LOCAL = Vector(SPOUT[-1])

def pot_matrix(tilt, tip_world=None, base_world=None):
    R = Matrix.Rotation(tilt, 4, 'Y')
    if tip_world is not None:
        return Matrix.Translation(tip_world - (R @ SPOUT_TIP_LOCAL)) @ R
    return Matrix.Translation(base_world) @ R

def build_pot(mat, coffee_mat=None):
    parts = [obj('pot_body', lathe_mesh('pot_body', POT_PROFILE, 160), mat)]
    radii = list(np.linspace(1.15, 0.55, len(SPOUT)))
    parts.append(tube('pot_spout', SPOUT, radii, mat))
    arc = [(-5.6 - 2.6 * math.sin(a), 0, 7.3 + 4.2 * math.cos(a)) for a in np.linspace(0.08 * math.pi, 0.92 * math.pi, 30)]
    parts.append(tube('pot_handle', arc, [0.55] * len(arc), mat))
    lid = obj('pot_lid', lathe_mesh('pot_lid', [(0.0, 14.2), (3.7, 14.2), (3.9, 14.6), (2.0, 15.4), (0.9, 15.6), (1.0, 16.4),
                                                (0.7, 16.9), (0.0, 17.0)], 96), mat)
    parts.append(lid)
    root = bpy.data.objects.new('pot', None); bpy.context.collection.objects.link(root)
    for p in parts: p.parent = root
    return root

# ---------------- milk jug (local: base centre at origin, lip towards +x) ----------------
JUG_PROFILE = [(0.0, 0.0), (2.6, 0.0), (2.9, 0.4), (3.1, 2.5), (2.7, 5.5), (2.5, 7.2), (2.65, 7.8), (2.45, 7.9), (2.25, 7.6),
               (2.28, 7.2), (2.48, 5.5), (2.86, 2.5), (2.66, 0.55), (2.3, 0.3), (0.0, 0.3)]          # open, 2-3 mm wall
JUG_TIP_LOCAL = Vector((3.4, 0, 7.9))

def jug_matrix(tilt, tip_world=None, base_world=None):
    # the jug pours towards -x: mirror the local frame with a 180 deg turn about z, then tilt
    R = Matrix.Rotation(math.pi, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'Y')
    if tip_world is not None:
        return Matrix.Translation(tip_world - (R @ JUG_TIP_LOCAL)) @ R
    return Matrix.Translation(base_world) @ R

def build_jug(mat):
    parts = [obj('jug_body', lathe_mesh('jug_body', JUG_PROFILE, 128), mat)]
    lip = bezier((2.4, 0, 7.75), (2.9, 0, 7.85), (3.2, 0, 7.9), (3.4, 0, 7.9), 10)   # sits on the rim, outside the opening
    parts.append(tube('jug_lip', lip, list(np.linspace(0.42, 0.3, len(lip))), mat))
    arc = [(-2.3 - 1.8 * math.sin(a), 0, 4.0 + 2.4 * math.cos(a)) for a in np.linspace(0.0, math.pi, 28)]   # ends sink into the body
    parts.append(tube('jug_handle', arc, [0.35] * len(arc), mat))
    root = bpy.data.objects.new('jug', None); bpy.context.collection.objects.link(root)
    for p in parts: p.parent = root
    return root

def write_stl(path, me, scale=0.01):
    """Binary STL of a mesh (triangulated), scaled from cm to metres for OpenFOAM."""
    import struct
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces)
    with open(path, 'wb') as f:
        f.write(b'mug'.ljust(80, b' ')); f.write(struct.pack('<I', len(bm.faces)))
        for fc in bm.faces:
            n = fc.normal
            f.write(struct.pack('<3f', n.x, n.y, n.z))
            for v in fc.verts:
                f.write(struct.pack('<3f', *(c * scale for c in v.co)))
            f.write(b'\0\0')
    bm.free()

if __name__ == '__main__':
    import sys, os
    if '--' in sys.argv: sys.argv = [sys.argv[0]] + sys.argv[sys.argv.index('--') + 1:]
    out = sys.argv[1] if len(sys.argv) > 1 else 'geometry'
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    write_stl(os.path.join(out, 'mug.stl'), lathe_mesh('mug', MUG_PROFILE, 160))
    M = pot_matrix(POT_TILT, tip_world=P_TIP)
    d = (M.to_3x3() @ (Vector(SPOUT[-1]) - Vector(SPOUT[-2]))).normalized()
    Mj = jug_matrix(JUG_TILT, tip_world=M_TIP)
    dj = (Mj.to_3x3() @ Vector((1.0, 0, 0.35))).normalized()
    print('spout tip', tuple(round(c, 3) for c in P_TIP), 'spout direction', tuple(round(c, 3) for c in d))
    print('pot base (world)', tuple(round(c, 2) for c in M.translation))
    print('jug tip', tuple(M_TIP), 'jug lip direction', tuple(round(c, 3) for c in dj))
