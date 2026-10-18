"""Morning coffee v2: real ceramic pot, mug and milk jug; 3D OpenFOAM pour and milk; cut-away cross-section.

Shots (24 fps):
  establish  60 fr  wide: pot and jug on the table, mug with coffee, steam, sun through the window
  pour       86 fr  pot tilted, 3D interFoam coffee stream and surface (iso-surface meshes)
  milk       96 fr  jug pouring, coffee surface coloured by the simulated near-surface milk
  cross      96 fr  cut-away mug: the simulated milk field on the cut plane y = 0
Usage:
  python3.13 scene2.py still SHOT FRAME RES_X RES_Y SAMPLES OUT.png
  python3.13 scene2.py anim  SHOT RES_X RES_Y SAMPLES OUTDIR [STEP]        (STEP=2 renders every 2nd frame)
"""
import sys, os, math, numpy as np, bpy, bmesh
from mathutils import Matrix, Vector
if '--' in sys.argv: sys.argv = [sys.argv[0]] + sys.argv[sys.argv.index('--') + 1:]
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D); sys.path.insert(0, os.path.dirname(D))
import models as M
import coffee_scene as CS          # room, lights, haze, steam volume, image helpers
CS.SEQ = os.path.join(os.path.dirname(D), 'seq')
SEQ2 = os.path.join(D, 'seq2')
FPS = 24
SHOTS = {'establish': 60, 'pour': 110, 'milk': 96, 'cross': 96}
T_PHYS0 = {'establish': 0.0, 'pour': 2.5, 'milk': 7.1, 'cross': 7.1}   # physical film time at the shot's first frame (cross replays the milk)
MILK_POUR = 3.0                                                          # s of milk inflow (mk_milk3d.py T_OFF)
LEVEL0, LEVEL1 = 5.2, 6.6

def mats():
    mug = CS.principled('mug_ceramic', (0.86, 0.85, 0.81), 0.12, **{'Coat Weight': 0.6, 'Subsurface Weight': 0.08})
    pot = CS.principled('pot_glaze', (0.035, 0.085, 0.20), 0.08, **{'Coat Weight': 1.0, 'Coat Roughness': 0.03})
    jug = CS.principled('jug_glaze', (0.80, 0.72, 0.58), 0.15, **{'Coat Weight': 0.8})
    coffee = CS.principled('coffee_liquid', (0.035, 0.016, 0.007), 0.04, **{'Subsurface Weight': 0.25,
                           'Subsurface Radius': (0.9, 0.35, 0.12), 'Subsurface Scale': 0.4, 'IOR': 1.34})
    milk = CS.principled('milk_liquid', (0.96, 0.955, 0.93), 0.2, **{'Subsurface Weight': 0.5, 'Subsurface Radius': (1.0, 0.95, 0.85), 'Subsurface Scale': 0.1})   # neutral white (default radius is red-heavy)
    return dict(mug=mug, pot=pot, jug=jug, coffee=coffee, milk=milk)

ASSETS = os.path.join(D, 'assets')
def import_glb(name, keep=None, drop=(), recenter=None):
    """Import a glTF asset (the importer converts metres to scene units, cm) under an empty; optionally keep only some meshes and re-centre on one of them."""
    path = os.path.join(ASSETS, name + '.glb')
    if not os.path.exists(path): return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in list(new):                                  # assets may bring their own cameras and lights
        if o.type in ('CAMERA', 'LIGHT'):
            new.remove(o); bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.scene.camera = None
    for o in list(new):
        if o.type == 'MESH' and ((keep and o.name not in keep) or any(o.name.startswith(d) for d in drop)):
            new.remove(o); bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    off = Vector((0, 0, 0))
    if recenter:
        o = bpy.data.objects[recenter]; bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        off = Vector((sum(v.x for v in bb) / 8, sum(v.y for v in bb) / 8, 0))
    root = bpy.data.objects.new(name, None); bpy.context.collection.objects.link(root)
    for o in new:
        if o.parent is None or o.parent not in new:
            mw = o.matrix_world.copy(); o.parent = root; o.matrix_world = Matrix.Translation(-off) @ mw
    return root

def decorate():
    """Free assets from the Khronos glTF Sample Assets: GlassVaseFlowers (CC0),
    DiffuseTransmissionPlant (CC-BY 4.0, Eric Chadwick / Darmstadt Graphics Group)."""
    v = import_glb('GlassVaseFlowers', keep=('GlassTransmission', 'Flowers2'), recenter='GlassTransmission')
    if v: v.scale = (1, 1, 1); v.location = (-50, 34, -M.BASE); v.rotation_euler = (0, 0, math.radians(20))
    p = import_glb('DiffuseTransmissionPlant', drop=('firefly',))
    if p: p.scale = (0.48, 0.48, 0.48); p.location = (30, 32, -M.BASE); p.rotation_euler = (0, 0, math.radians(-30))

def image_material(name, img, gloss=True, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; N = m.node_tree.nodes; L = m.node_tree.links
    p = N['Principled BSDF']; tx = N.new('ShaderNodeTexImage'); tx.image = img; tx.interpolation = 'Linear'; tx.extension = 'EXTEND'
    uv = N.new('ShaderNodeTexCoord'); L.new(uv.outputs['UV'], tx.inputs['Vector'])
    L.new(tx.outputs['Color'], p.inputs['Base Color'])
    p.inputs['Roughness'].default_value = 0.04 if gloss else 0.6
    p.inputs['Coat Weight'].default_value = 1.0 if gloss else 0.0
    if emit > 0:
        L.new(tx.outputs['Color'], p.inputs['Emission Color']); p.inputs['Emission Strength'].default_value = emit
    return m

def color_image(name, rgb):
    h, w, _ = rgb.shape
    img = bpy.data.images.new(name, width=w, height=h, alpha=True, float_buffer=True)
    try: img.colorspace_settings.name = 'Linear Rec.709'
    except Exception: pass
    set_rgb(img, rgb); return img

def set_rgb(img, rgb):
    a = np.concatenate([np.asarray(rgb, np.float32), np.ones(rgb.shape[:2] + (1,), np.float32)], axis=-1)
    img.pixels.foreach_set(a.ravel()); img.update()

def disc(name, radius, z, mat, segs=128):
    """Flat disc with planar UVs spanning [-4, 4] cm."""
    bm = bmesh.new(); c = bm.verts.new((0, 0, z))
    ring = [bm.verts.new((radius * math.cos(2 * math.pi * k / segs), radius * math.sin(2 * math.pi * k / segs), z)) for k in range(segs)]
    for k in range(segs): bm.faces.new((c, ring[k], ring[(k + 1) % segs]))
    uvl = bm.loops.layers.uv.new()
    for f in bm.faces:
        for lp in f.loops: lp[uvl].uv = ((lp.vert.co.x + 4.0) / 8.0, (lp.vert.co.y + 4.0) / 8.0)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = M.obj(name, me, mat); return ob

def coffee_body(level, top_mat, side_mat):
    """Resting coffee: closed cylinder (into the ceramic by 0.4 mm), top face with its own (image) material."""
    ob = disc('coffee_top', M.R_IN + 0.04, level, top_mat)
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=M.R_IN + 0.04, depth=level - 0.01, location=(0, 0, (level - 0.01) / 2 - 0.005))
    body = bpy.context.object; body.data.materials.append(side_mat)
    return ob, body

def cut_mug(me):
    """Keep the y > 0 half of the mug and close the cut faces."""
    bm = bmesh.new(); bm.from_mesh(me)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0), plane_no=(0, -1, 0), clear_outer=True)
    edges = [e for e in bm.edges if e.is_boundary]
    bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    out = bpy.data.meshes.new('mug_cut'); bm.to_mesh(out); bm.free()
    for f in out.polygons: f.use_smooth = abs(f.normal.y) < 0.9
    return out

def section_plane(img, H, mat_name='section'):
    bm = bmesh.new(); r = M.R_IN
    vs = [bm.verts.new(p) for p in ((-r, -0.001, 0), (r, -0.001, 0), (r, -0.001, H), (-r, -0.001, H))]
    f = bm.faces.new(vs); uvl = bm.loops.layers.uv.new()
    for lp in f.loops: lp[uvl].uv = ((lp.vert.co.x + r) / (2 * r), lp.vert.co.z / H)
    me = bpy.data.meshes.new('section'); bm.to_mesh(me); bm.free()
    return M.obj('section', me, image_material(mat_name, img, gloss=False, emit=0.35))

def milk_stream(mat, t_frac):
    """Milk stream from the jug lip to the coffee surface (projectile path; scene geometry, not simulated)."""
    v0 = np.array([-0.284, 0.0, -0.204]) * 100; g = np.array([0, 0, -981.0]); p0 = np.array(M.M_TIP)
    ts = np.linspace(0, 0.0862, 20); pts = [p0 + v0 * t + 0.5 * g * t * t for t in ts]
    rad = list(np.linspace(0.33, 0.24, len(pts)) * t_frac)
    return M.tube('milk_stream', pts, rad, mat, sides=24)

def atlas_steam(atlas_npz, gain):
    """Volume box whose density is read from a 3D field packed as z-slices in a 2D atlas image (trilinear)."""
    box = atlas_npz['box'] * 100.0; nx, ny, nz = (int(v) for v in atlas_npz['n']); cols = int(atlas_npz['cols']); rows = int(np.ceil(nz / cols))
    img = CS.float_image('steam_atlas', atlas_npz['atlas'][0].astype(np.float32))
    m = bpy.data.materials.new('steam3d'); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
    for nd in list(N): N.remove(nd)
    def op(o, a, b=None):
        nd = N.new('ShaderNodeMath'); nd.operation = o
        for i, x in enumerate((a, b)):
            if x is None: continue
            if isinstance(x, (int, float)): nd.inputs[i].default_value = x
            else: L.new(x, nd.inputs[i])
        return nd.outputs[0]
    tc = N.new('ShaderNodeTexCoord'); sp = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Generated'], sp.inputs[0])
    u, v, w = sp.outputs[0], sp.outputs[1], sp.outputs[2]
    fz = op('MULTIPLY', w, nz - 1.0); i0 = op('FLOOR', fz); frac = op('SUBTRACT', fz, i0)
    i1 = op('MINIMUM', op('ADD', i0, 1.0), nz - 1.0)
    uu = op('DIVIDE', op('ADD', op('MULTIPLY', u, nx - 1.0), 0.5), float(nx))
    vv = op('DIVIDE', op('ADD', op('MULTIPLY', v, ny - 1.0), 0.5), float(ny))
    def look(i):
        col = op('FLOORED_MODULO', i, float(cols)); row = op('FLOOR', op('DIVIDE', i, float(cols)))
        U = op('DIVIDE', op('ADD', col, uu), float(cols)); V = op('DIVIDE', op('ADD', row, vv), float(rows))
        cv = N.new('ShaderNodeCombineXYZ'); L.new(U, cv.inputs[0]); L.new(V, cv.inputs[1])
        tx = N.new('ShaderNodeTexImage'); tx.image = img; tx.interpolation = 'Linear'; tx.extension = 'EXTEND'
        L.new(cv.outputs[0], tx.inputs['Vector'])
        sc = N.new('ShaderNodeSeparateColor'); L.new(tx.outputs['Color'], sc.inputs[0]); return sc.outputs[0]
    a0, a1 = look(i0), look(i1)
    val = op('ADD', op('MULTIPLY', a0, op('SUBTRACT', 1.0, frac)), op('MULTIPLY', a1, frac))
    dens = op('MULTIPLY', val, gain)
    vs = N.new('ShaderNodeVolumeScatter'); vs.inputs['Color'].default_value = (1, 1, 1, 1); vs.inputs['Anisotropy'].default_value = 0.65
    L.new(dens, vs.inputs['Density'])
    out = N.new('ShaderNodeOutputMaterial'); L.new(vs.outputs[0], out.inputs['Volume'])
    c = 0.5 * (box[:, 0] + box[:, 1]); size = box[:, 1] - box[:, 0]
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(c)); ob = bpy.context.object; ob.name = 'steam3d'
    ob.scale = tuple(size); ob.data.materials.append(m); ob.visible_shadow = False
    return img

CAMS = {  # location, target, lens, f-stop
    'establish': ((30, -70, 34), (-6, 0, 8), 45, 4.0),
    'pour':      ((12, -42, 31), (-4.0, 0, 10.0), 40, 2.8),
    'milk':      ((4, -42, 27), (2.0, 0, 8.5), 45, 2.8),
    'cross':     ((3.0, -44, 13), (0, 0, 4.0), 50, 4.0),
}
def camera(shot, k=0):
    loc, tgt, lens, fs = CAMS[shot]
    loc = np.array(loc, float)
    if shot == 'cross':                                    # slow dolly in
        loc = loc + np.array([-1.5, 10.0, -2.5]) * min(1.0, k / SHOTS[shot])
    cam = bpy.context.scene.camera
    if cam is None:
        bpy.ops.object.camera_add(); cam = bpy.context.object; bpy.context.scene.camera = cam
    cam.location = loc; d = np.array(tgt) - loc
    cam.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    cam.data.lens = lens; cam.data.dof.use_dof = True; cam.data.dof.focus_distance = float(np.linalg.norm(d))
    cam.data.dof.aperture_fstop = fs / 100; cam.data.clip_start = 0.5; cam.data.clip_end = 2000

def place(root, matrix): root.matrix_world = matrix

def render_shot(shot, frames, rx, ry, spp, out_fn):
    sc = CS.setup(rx, ry, spp); CS.build_room(); m = mats(); decorate()
    mug_me = M.lathe_mesh('mug', M.MUG_PROFILE, 160)
    if shot == 'cross':
        mug = M.obj('mug', cut_mug(mug_me), m['mug'])
    else:
        mug = M.obj('mug', mug_me, m['mug'])
        arc = [(M.R_OUT - 0.25 + 2.2 * math.sin(a), 0, 4.3 + 2.6 * math.cos(a)) for a in np.linspace(0.02 * math.pi, 0.98 * math.pi, 32)]   # ends sink into the wall
        h = M.tube('mug_handle', arc, [0.42] * len(arc), m['mug']); h.scale = (1.0, 1.25, 1.0)
    pot = M.build_pot(m['pot']); jug = M.build_jug(m['jug'])
    for p in pot.children: p.data.materials.clear(); p.data.materials.append(m['pot'])
    for p in jug.children: p.data.materials.clear(); p.data.materials.append(m['jug'])
    on_table_pot = Matrix.Translation((-20, 9, -M.BASE)) @ Matrix.Rotation(math.radians(-25), 4, 'Z')
    on_table_jug = Matrix.Translation((15, 10, -M.BASE)) @ Matrix.Rotation(math.radians(200), 4, 'Z')
    place(pot, M.pot_matrix(M.POT_TILT, tip_world=M.P_TIP) if shot == 'pour' else on_table_pot)
    place(jug, M.jug_matrix(M.JUG_TILT, tip_world=M.M_TIP) if shot in ('milk', 'cross') else on_table_jug)
    camera(shot)
    # steam
    st_path = os.path.join(SEQ2, 'steam_atlas.npz'); steam = np.load(st_path) if os.path.exists(st_path) else None; st_img = None
    if steam is not None:   # physical extinction of 2 um droplets: beta = 3 LWC / (2 rho_w r), LWC = rho_air * fog
        st_img = atlas_steam(steam, 1.5 * 1.1 / (1000.0 * 2e-6) / 100.0)
    # liquids
    milk = np.load(os.path.join(SEQ2, 'milk.npz')) if os.path.exists(os.path.join(SEQ2, 'milk.npz')) else None
    pour_t = np.load(os.path.join(SEQ2, 'pour', 't.npy')) if os.path.exists(os.path.join(SEQ2, 'pour', 't.npy')) else None
    top_img = sec_img = None; liquid = stream = None
    if shot in ('milk', 'cross') and milk is not None:
        top_img = color_image('top', milk['top'][0].astype(np.float32))
        if shot == 'milk':
            coffee_body(LEVEL1, image_material('coffee_top', top_img), m['coffee'])
        else:                                   # cut-away: only the back half of the surface; the section is the cut face
            top = disc('coffee_top', M.R_IN + 0.04, LEVEL1, image_material('coffee_top', top_img))
            bm = bmesh.new(); bm.from_mesh(top.data)
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(0, -1, 0), clear_outer=True)
            bm.to_mesh(top.data); bm.free()
        if shot == 'cross':
            sec_img = color_image('sec', milk['sec'][0].astype(np.float32)); section_plane(sec_img, float(milk['H']) * 100)
    for k in frames:
        t = k / FPS
        if st_img is not None:
            i = int(np.argmin(np.abs(steam['t'] - (T_PHYS0[shot] + t)))); CS.set_image(st_img, steam['atlas'][i].astype(np.float32))
        if shot == 'pour' and pour_t is not None:
            if liquid is not None: bpy.data.objects.remove(liquid, do_unlink=True)
            i = int(np.argmin(np.abs(pour_t - t)))
            bpy.ops.wm.stl_import(filepath=os.path.join(SEQ2, 'pour', f'{i:04d}.stl'))
            liquid = bpy.context.selected_objects[0]; liquid.scale = (100, 100, 100)
            liquid.data.materials.clear(); liquid.data.materials.append(m['coffee'])
            for f in liquid.data.polygons: f.use_smooth = True
        if shot in ('milk', 'cross') and milk is not None:
            i = int(np.argmin(np.abs(milk['t'] - t)))
            set_rgb(top_img, milk['top'][i].astype(np.float32))
            if sec_img is not None: set_rgb(sec_img, milk['sec'][i].astype(np.float32))
            if stream is not None: bpy.data.objects.remove(stream, do_unlink=True); stream = None
            frac = 1.0 if t < MILK_POUR - 0.05 else max(0.0, 1 - (t - MILK_POUR + 0.05) / 0.1)
            if frac > 0.02: stream = milk_stream(m['milk'], frac)
        camera(shot, k)
        if os.environ.get('RESUME') and os.path.exists(out_fn(k)): continue
        sc.render.filepath = out_fn(k); bpy.ops.render.render(write_still=True); print('rendered', shot, k, flush=True)

# ---------------- continuous film: one take on one physical clock, camera glides between the shot framings ----------------
FILM = 266                     # establish 0-59, pour 60-169, milk 170-265; film time = steam time (steam result ends at 11.08 s)
F_POUR, F_MILK = 60, 170
POUR_STOP = 96                 # pour frame at which the stream leaves the spout for good
CAM_KEYS = [(0, 'establish', 0), (20, 'establish', 0), (62, 'pour', 0), (150, 'pour', 0), (184, 'milk', 0), (198, 'milk', 0),
            (230, 'cross', 0), (265, 'cross', 1)]          # (film frame, framing, dolly fraction)
FADE = (204, 228)              # film frames over which the front half of the mug and coffee fades out (cut-away reveal)
SETTLE = (162, 180)            # the simulated pour surface dissolves into the resting surface of the milk part

def smooth(x): x = min(1.0, max(0.0, x)); return x * x * (3 - 2 * x)

def cam_path():
    """Monotone cubic (PCHIP) through the camera keys: C1-smooth moves that settle on each framing, no overshoot."""
    from scipy.interpolate import PchipInterpolator
    fr, rows = [], []
    for f, shot, s in CAM_KEYS:
        loc, tgt, lens, fs = CAMS[shot]; loc = np.array(loc, float)
        if shot == 'cross': loc = loc + np.array([-1.5, 10.0, -2.5]) * s
        fr.append(f); rows.append(np.concatenate([loc, tgt, [lens, fs]]))
    return PchipInterpolator(np.array(fr, float), np.array(rows), axis=0, extrapolate=False)

def film_camera(path, f):
    v = path(min(max(f, CAM_KEYS[0][0]), CAM_KEYS[-1][0])); loc, tgt, lens, fs = v[:3], v[3:6], v[6], v[7]
    cam = bpy.context.scene.camera
    if cam is None:
        bpy.ops.object.camera_add(); cam = bpy.context.object; bpy.context.scene.camera = cam
    cam.location = loc; d = tgt - loc
    cam.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    cam.data.lens = lens; cam.data.dof.use_dof = True; cam.data.dof.focus_distance = float(np.linalg.norm(d))
    cam.data.dof.aperture_fstop = fs / 100; cam.data.clip_start = 0.5; cam.data.clip_end = 2000

def blend_pose(A, B, s, pivot, lift):
    """Move a rigid body from pose A to pose B: its pivot point travels on a straight line raised by an arc, the rotation is slerped."""
    qa, qb = A.to_quaternion(), B.to_quaternion(); q = qa.slerp(qb, s); R = q.to_matrix().to_4x4()
    pa, pb = A @ pivot, B @ pivot; p = pa.lerp(pb, s) + Vector((0, 0, lift * math.sin(math.pi * s)))
    return Matrix.Translation(p - R.to_3x3() @ pivot) @ R

def fade_material(src):
    """Copy of a material whose surface can be mixed to fully transparent through a Value node (returned)."""
    m = src.copy(); m.name = src.name + '_fade'; N = m.node_tree.nodes; L = m.node_tree.links
    out = next(n for n in N if n.type == 'OUTPUT_MATERIAL'); shader = out.inputs['Surface'].links[0].from_socket
    mix = N.new('ShaderNodeMixShader'); tr = N.new('ShaderNodeBsdfTransparent'); val = N.new('ShaderNodeValue'); val.outputs[0].default_value = 0.0
    L.new(val.outputs[0], mix.inputs[0]); L.new(shader, mix.inputs[1]); L.new(tr.outputs[0], mix.inputs[2]); L.new(mix.outputs[0], out.inputs['Surface'])
    return m, val.outputs[0]

def half(me, name, front, cap):
    """Front (y < 0) or back (y > 0) half of a mesh, cut at y = 0; the cut is closed when cap."""
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(0, 1 if front else -1, 0), clear_outer=True)
    if cap: bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    out = bpy.data.meshes.new(name); bm.to_mesh(out); bm.free()
    for f in out.polygons: f.use_smooth = abs(f.normal.y) < 0.9
    return out

def render_film(frames, rx, ry, spp, out_fn):
    sc = CS.setup(rx, ry, spp); CS.build_room(); m = mats(); decorate()
    if os.environ.get('VOL_STEP'): sc.cycles.volume_step_rate = float(os.environ['VOL_STEP'])   # fast preview knobs
    if os.environ.get('BOUNCES'): sc.cycles.max_bounces = sc.cycles.transmission_bounces = int(os.environ['BOUNCES'])
    if os.environ.get('HAZE') == '0':
        for o in bpy.data.objects:
            if o.type == 'MESH' and any(ms and ms.name == 'haze' for ms in o.data.materials): o.hide_render = True
    mug_me = M.lathe_mesh('mug', M.MUG_PROFILE, 160)
    arc =[(M.R_OUT - 0.25 + 2.2 * math.sin(a), 0, 4.3 + 2.6 * math.cos(a)) for a in np.linspace(0.02 * math.pi, 0.98 * math.pi, 32)]   # ends sink into the wall
    mug = M.obj('mug', mug_me, m['mug'])
    handle = M.tube('mug_handle', arc, [0.42] * len(arc), m['mug']); handle.scale = (1.0, 1.25, 1.0)
    # cut-away pieces: capped back halves, open front halves that fade out
    mug_fade, f_mug = fade_material(m['mug'])
    mug_b = M.obj('mug_back', half(mug_me, 'mug_back', False, True), m['mug'])
    mug_f = M.obj('mug_front', half(mug_me, 'mug_front', True, False), mug_fade)
    hnd_b = M.obj('handle_back', half(handle.data, 'handle_back', False, True), m['mug']); hnd_b.scale = handle.scale
    hnd_f = M.obj('handle_front', half(handle.data, 'handle_front', True, False), mug_fade); hnd_f.scale = handle.scale
    pot = M.build_pot(m['pot']); jug = M.build_jug(m['jug'])
    for p in pot.children: p.data.materials.clear(); p.data.materials.append(m['pot'])
    for p in jug.children: p.data.materials.clear(); p.data.materials.append(m['jug'])
    pot_table = Matrix.Translation((-20, 9, -M.BASE)) @ Matrix.Rotation(math.radians(-25), 4, 'Z')
    jug_table = Matrix.Translation((15, 10, -M.BASE)) @ Matrix.Rotation(math.radians(200), 4, 'Z')
    pot_pour = M.pot_matrix(M.POT_TILT, tip_world=M.P_TIP); jug_pour = M.jug_matrix(M.JUG_TILT, tip_world=M.M_TIP)
    path = cam_path()
    st_path = os.path.join(SEQ2, 'steam_atlas.npz'); steam = np.load(st_path) if os.path.exists(st_path) else None; st_img = None
    if steam is not None:   # physical extinction of 2 um droplets: beta = 3 LWC / (2 rho_w r), LWC = rho_air * fog
        st_img = atlas_steam(steam, 1.5 * 1.1 / (1000.0 * 2e-6) / 100.0)
    milk = np.load(os.path.join(SEQ2, 'milk.npz'))
    pour_t = np.load(os.path.join(SEQ2, 'pour', 't.npy'))
    # resting coffee for the milk part: whole (before the reveal) and as halves (during and after it)
    top_img = color_image('top', milk['top'][0].astype(np.float32)); sec_img = color_image('sec', milk['sec'][0].astype(np.float32))
    top_mat = image_material('coffee_top', top_img); top_fade, f_top = fade_material(top_mat); cof_fade, f_cof = fade_material(m['coffee']); liq_fade, f_liq = fade_material(m['coffee'])
    top, body = coffee_body(LEVEL1, top_mat, m['coffee'])
    top_b = M.obj('coffee_top_back', half(top.data, 'coffee_top_back', False, False), top_mat)
    top_f = M.obj('coffee_top_front', half(top.data, 'coffee_top_front', True, False), top_fade)
    body_f = M.obj('coffee_body_front', half(body.data, 'coffee_body_front', True, False), cof_fade); body_f.location = body.location
    for o in (body_f,):
        for p in o.data.polygons: p.use_smooth = False
    section = section_plane(sec_img, float(milk['H']) * 100)
    liquid = stream = None
    for f in frames:
        t = f / FPS
        if st_img is not None:
            i = int(np.argmin(np.abs(steam['t'] - t))); CS.set_image(st_img, steam['atlas'][i].astype(np.float32))
        # pot: lifted into the pour before it starts, set back once the stream has left the spout
        s = smooth((f - 22) / (F_POUR - 2 - 22)) - smooth((f - (F_POUR + POUR_STOP + 1)) / 32)
        place(pot, blend_pose(pot_table, pot_pour, s, Vector((0, 0, 7)), 6.0))
        place(jug, blend_pose(jug_table, jug_pour, smooth((f - 130) / (F_MILK - 1 - 130)), Vector((0, 0, 4)), 4.0))
        # coffee
        if liquid is not None: bpy.data.objects.remove(liquid, do_unlink=True); liquid = None
        settle = smooth((f - SETTLE[0]) / (SETTLE[1] - SETTLE[0])); f_liq.default_value = settle
        if F_POUR <= f < SETTLE[1]:
            i = int(np.argmin(np.abs(pour_t - (f - F_POUR) / FPS)))   # holds the last surface after the pour result ends
            bpy.ops.wm.stl_import(filepath=os.path.join(SEQ2, 'pour', f'{i:04d}.stl'))
            liquid = bpy.context.selected_objects[0]; liquid.scale = (100, 100, 100)
            liquid.data.materials.clear(); liquid.data.materials.append(liq_fade)
            for p in liquid.data.polygons: p.use_smooth = True
        km = f - F_MILK; tm = km / FPS
        if km >= 0:
            i = int(np.argmin(np.abs(milk['t'] - tm)))
            set_rgb(top_img, milk['top'][i].astype(np.float32)); set_rgb(sec_img, milk['sec'][i].astype(np.float32))
        if stream is not None: bpy.data.objects.remove(stream, do_unlink=True); stream = None
        if km >= 0:
            frac = 1.0 if tm < MILK_POUR - 0.05 else max(0.0, 1 - (tm - MILK_POUR + 0.05) / 0.1)
            if frac > 0.02: stream = milk_stream(m['milk'], frac)
        # cut-away reveal
        a = smooth((f - FADE[0]) / (FADE[1] - FADE[0])); split = f >= FADE[0]
        for o in (mug, handle, top, body): o.hide_render = split or (o in (top, body) and f < SETTLE[0])
        for o in (mug_b, hnd_b, top_b, section): o.hide_render = not split
        for o in (mug_f, hnd_f, top_f, body_f): o.hide_render = not split or a >= 1.0
        for v in (f_mug, f_top, f_cof): v.default_value = a
        film_camera(path, f)
        if os.environ.get('RESUME') and os.path.exists(out_fn(f)): continue
        sc.render.filepath = out_fn(f); bpy.ops.render.render(write_still=True); print('rendered film', f, flush=True)

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode in ('film', 'filmstill'):
        # film      RES_X RES_Y SAMPLES OUTDIR [STEP] [F0 F1]
        # filmstill FRAME RES_X RES_Y SAMPLES OUT.png
        if mode == 'filmstill':
            k, rx, ry, spp, out = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
            render_film([k], rx, ry, spp, lambda _: out)
        else:
            rx, ry, spp, outdir = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), os.path.abspath(sys.argv[5])   # Blender resolves relative paths against the drive root
            step = int(sys.argv[6]) if len(sys.argv) > 6 else 1
            f0, f1 = (int(sys.argv[7]), int(sys.argv[8])) if len(sys.argv) > 8 else (0, FILM)
            os.makedirs(outdir, exist_ok=True)
            render_film(range(f0, f1, step), rx, ry, spp, lambda k: os.path.join(outdir, f'film_{k:04d}.png'))
    elif mode == 'still':
        shot, k, rx, ry, spp, out = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
        render_shot(shot, [k], rx, ry, spp, lambda _: out)
    else:
        shot, rx, ry, spp, outdir = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
        step = int(sys.argv[7]) if len(sys.argv) > 7 else 1
        os.makedirs(outdir, exist_ok=True)
        render_shot(shot, range(0, SHOTS[shot], step), rx, ry, spp, lambda k: os.path.join(outdir, f'{shot}_{k:04d}.png'))
