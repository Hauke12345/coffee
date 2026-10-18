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

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'still':
        shot, k, rx, ry, spp, out = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
        render_shot(shot, [k], rx, ry, spp, lambda _: out)
    else:
        shot, rx, ry, spp, outdir = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
        step = int(sys.argv[7]) if len(sys.argv) > 7 else 1
        os.makedirs(outdir, exist_ok=True)
        render_shot(shot, range(0, SHOTS[shot], step), rx, ry, spp, lambda k: os.path.join(outdir, f'{shot}_{k:04d}.png'))
