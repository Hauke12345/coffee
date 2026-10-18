"""Morning coffee scene in Blender Cycles, driven by OpenFOAM results.

Shots (24 fps):
  1 establish  2.00 s   wide, cup with coffee (52 mm), steam rising, sun through the window
  2 pour       3.75 s   close-up, coffee poured from above (interFoam, axisymmetric) - liquid surface by marching cubes
  3 milk       4.00 s   milk stream into the full cup (twoLiquidMixingFoam, axisymmetric) - milk cloud as scattering volume
Steam (rhoReactingBuoyantFoam, condensed water) runs continuously through all shots.

Usage:
  python3.13 coffee_scene.py still SHOT FRAME RES_X RES_Y SAMPLES OUT.png
  python3.13 coffee_scene.py anim  SHOT RES_X RES_Y SAMPLES OUTDIR [first] [last]
  (or: blender -b -P coffee_scene.py -- <same arguments>)     CANDLE_GPU=1 renders on an NVIDIA GPU.
Units: 1 Blender unit = 1 cm. Cup inner bottom at z = 0; inner radius 4.0 cm; rim at 8.5 cm.
"""
import sys, os, math, numpy as np, bpy, bmesh

if '--' in sys.argv: sys.argv = [sys.argv[0]] + sys.argv[sys.argv.index('--') + 1:]
D = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(D, 'seq')
FPS = 24
SHOTS = {'establish': 48, 'pour': 84, 'milk': 96}
STEAM_T0 = {'establish': 2.0, 'pour': 4.0, 'milk': 7.5}       # steam simulation time at the shot's first frame
R_IN, R_OUT, Z_RIM, BASE = 4.0, 4.45, 8.5, 0.6
LEVEL0, LEVEL1 = 5.2, None                                       # coffee level before / after the pour (cm)

def load(name):
    p = os.path.join(SEQ, name + '.npz')
    return np.load(p) if os.path.exists(p) else None

# ------------------------------------------------------------------ scene setup
def setup(res_x, res_y, spp):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 0.01
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
    if os.environ.get('CANDLE_GPU'):
        try:
            prefs = bpy.context.preferences.addons['cycles'].preferences
            for backend in ('OPTIX', 'CUDA'):
                prefs.compute_device_type = backend; prefs.get_devices()
                if any(d.type == backend for d in prefs.devices):
                    for d in prefs.devices: d.use = d.type == backend
                    sc.cycles.device = 'GPU'; print('GPU:', backend); break
        except Exception as e:
            print('GPU setup failed:', e)
    sc.cycles.samples = spp; sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8; sc.cycles.transmission_bounces = 8; sc.cycles.volume_bounces = 1
    sc.cycles.volume_step_rate = 1.0
    sc.render.resolution_x, sc.render.resolution_y = res_x, res_y
    sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast' \
        if 'AgX - Medium High Contrast' in [l.identifier for l in sc.view_settings.bl_rna.properties['look'].enum_items] else 'None'
    sc.render.fps = FPS
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.020, 0.018, 0.016, 1)
    return sc

def principled(name, base, rough=0.4, **kw):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*base, 1); p.inputs['Roughness'].default_value = rough
    for k, v in kw.items():
        p.inputs[k].default_value = v
    return m

def lathe(name, profile, mat, steps=160):
    """Revolve an (r, z) polyline around the z axis."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(r, 0, z) for r, z in profile], [(i, i + 1) for i in range(len(profile) - 1)], [])
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    s = ob.modifiers.new('screw', 'SCREW'); s.angle = 2 * math.pi; s.steps = s.render_steps = steps; s.axis = 'Z'
    s.use_merge_vertices = True; s.use_smooth_shade = True
    ob.data.materials.append(mat)
    return ob

def build_room():
    wood = bpy.data.materials.new('wood'); wood.use_nodes = True
    nt = wood.node_tree; N = nt.nodes; L = nt.links; p = N['Principled BSDF']
    tc = N.new('ShaderNodeTexCoord'); mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (0.05, 0.6, 0.05)
    L.new(tc.outputs['Object'], mp.inputs['Vector'])
    wave = N.new('ShaderNodeTexWave'); wave.inputs['Scale'].default_value = 3.0; wave.inputs['Distortion'].default_value = 6.0
    wave.inputs['Detail'].default_value = 3.0; L.new(mp.outputs[0], wave.inputs['Vector'])
    ramp = N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (0.22, 0.11, 0.05, 1); ramp.color_ramp.elements[1].color = (0.42, 0.25, 0.13, 1)
    L.new(wave.outputs['Fac'], ramp.inputs['Fac']); L.new(ramp.outputs['Color'], p.inputs['Base Color'])
    p.inputs['Roughness'].default_value = 0.32; p.inputs['Coat Weight'].default_value = 0.25
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, -BASE)); t = bpy.context.object
    t.scale = (160, 120, 1); t.data.materials.append(wood)
    wall = principled('wall', (0.62, 0.58, 0.52), 0.8)
    # back wall at y = 45 with a window opening x in [-60, -8], z in [8, 75]
    def box(x0, x1, y0, y1, z0, z1, mat):
        bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        o = bpy.context.object; o.scale = (x1 - x0, y1 - y0, z1 - z0); o.data.materials.append(mat); return o
    Y, T = 45.0, 3.0
    box(-200, -60, Y, Y + T, -BASE, 150, wall); box(-8, 200, Y, Y + T, -BASE, 150, wall)
    box(-60, -8, Y, Y + T, -BASE, 8, wall); box(-60, -8, Y, Y + T, 75, 150, wall)
    frame = principled('frame', (0.85, 0.84, 0.80), 0.4)
    box(-35, -33, Y - 0.5, Y + 1.5, 8, 75, frame); box(-60, -8, Y - 0.5, Y + 1.5, 40.5, 42.5, frame)
    sky = bpy.data.materials.new('sky'); sky.use_nodes = True; N = sky.node_tree.nodes
    for n in list(N): N.remove(n)
    em = N.new('ShaderNodeEmission'); em.inputs[0].default_value = (0.75, 0.86, 1.0, 1); em.inputs[1].default_value = 2.5
    out = N.new('ShaderNodeOutputMaterial'); sky.node_tree.links.new(em.outputs[0], out.inputs['Surface'])
    bpy.ops.mesh.primitive_plane_add(size=1, location=(-30, 160, 40), rotation=(math.radians(90), 0, 0))
    s = bpy.context.object; s.scale = (400, 300, 1); s.data.materials.append(sky); s.visible_shadow = False
    # low morning sun, coming in through the window from behind-left
    bpy.ops.object.light_add(type='SUN')
    sun = bpy.context.object; sun.data.energy = 7.0; sun.data.angle = math.radians(0.6); sun.data.color = (1.0, 0.86, 0.68)
    sun.rotation_euler = (math.radians(68), 0, math.radians(200))
    # soft bounce light from the room behind the camera
    bpy.ops.object.light_add(type='AREA', location=(35, -90, 35)); fl = bpy.context.object
    fl.data.shape = 'RECTANGLE'; fl.data.size = 70; fl.data.size_y = 45; fl.data.energy = 9000; fl.data.color = (1.0, 0.9, 0.8)
    d = np.array((0, 0, 5)) - np.array(fl.location); fl.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    # light haze for visible sun shafts
    hz = bpy.data.materials.new('haze'); hz.use_nodes = True; N = hz.node_tree.nodes
    for n in list(N): N.remove(n)
    pv = N.new('ShaderNodeVolumePrincipled'); pv.inputs['Density'].default_value = 0.0007; pv.inputs['Anisotropy'].default_value = 0.55
    out = N.new('ShaderNodeOutputMaterial'); hz.node_tree.links.new(pv.outputs[0], out.inputs['Volume'])
    h = box(-120, 60, -90, Y - 0.6, -BASE + 0.01, 110, hz); h.visible_shadow = False

def build_cup():
    ceramic = principled('ceramic', (0.86, 0.85, 0.81), 0.12, **{'Coat Weight': 0.6, 'Subsurface Weight': 0.08})
    prof = [(0.0, -BASE), (R_OUT - 0.3, -BASE), (R_OUT - 0.1, -BASE + 0.05), (R_OUT, -BASE + 0.3), (R_OUT, Z_RIM - 0.15),
            (R_OUT - 0.05, Z_RIM - 0.03), ((R_IN + R_OUT) / 2, Z_RIM), (R_IN + 0.05, Z_RIM - 0.03), (R_IN, Z_RIM - 0.15),
            (R_IN, 0.25), (R_IN - 0.1, 0.06), (R_IN - 0.3, 0.0), (0.0, 0.0)]
    cup = lathe('cup', prof, ceramic)
    # handle: half torus on the +x side
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=False, radius=1.0, segments=48)
    me = bpy.data.meshes.new('h'); bm.to_mesh(me); bm.free()
    bpy.ops.mesh.primitive_torus_add(major_radius=2.1, minor_radius=0.42, major_segments=64, minor_segments=24,
                                     location=(R_OUT + 0.9, 0, 4.3), rotation=(math.radians(90), 0, 0))
    hd = bpy.context.object; hd.scale = (0.85, 1.25, 1.0)
    bm = bmesh.new(); bm.from_mesh(hd.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(-0.75, 0, 0), plane_no=(1, 0, 0), clear_inner=True)
    bm.to_mesh(hd.data); bm.free()
    for f in hd.data.polygons: f.use_smooth = True
    hd.data.materials.append(ceramic)
    return cup

# ------------------------------------------------------------------ liquids
def coffee_material(milk_img=None):
    """Coffee: glossy dielectric surface + strong brown absorption. With milk_img, milk scatters inside (r,z lookup)."""
    m = bpy.data.materials.new('coffee'); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
    p = N['Principled BSDF']; p.inputs['Base Color'].default_value = (1, 1, 1, 1)
    p.inputs['Transmission Weight'].default_value = 1.0; p.inputs['IOR'].default_value = 1.34; p.inputs['Roughness'].default_value = 0.03
    out = N['Material Output']
    absorb = N.new('ShaderNodeVolumeAbsorption'); absorb.inputs['Color'].default_value = (0.62, 0.36, 0.17, 1)
    if milk_img is None:
        absorb.inputs['Density'].default_value = 6.0
        L.new(absorb.outputs[0], out.inputs['Volume']); return m
    tc = N.new('ShaderNodeTexCoord'); sep = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sep.inputs[0])
    cxy = N.new('ShaderNodeCombineXYZ'); L.new(sep.outputs[0], cxy.inputs[0]); L.new(sep.outputs[1], cxy.inputs[1])
    ln = N.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'; L.new(cxy.outputs[0], ln.inputs[0])
    u = N.new('ShaderNodeMath'); u.operation = 'DIVIDE'; L.new(ln.outputs['Value'], u.inputs[0]); u.inputs[1].default_value = R_IN
    v = N.new('ShaderNodeMath'); v.operation = 'DIVIDE'; L.new(sep.outputs[2], v.inputs[0]); v.inputs[1].default_value = 7.5
    uv = N.new('ShaderNodeCombineXYZ'); L.new(u.outputs[0], uv.inputs[0]); L.new(v.outputs[0], uv.inputs[1])
    tx = N.new('ShaderNodeTexImage'); tx.image = milk_img; tx.interpolation = 'Linear'; tx.extension = 'EXTEND'
    L.new(uv.outputs[0], tx.inputs['Vector'])
    a = N.new('ShaderNodeSeparateColor'); L.new(tx.outputs['Color'], a.inputs[0])            # milk fraction in R
    one_minus = N.new('ShaderNodeMath'); one_minus.operation = 'SUBTRACT'; one_minus.inputs[0].default_value = 1.0
    L.new(a.outputs[0], one_minus.inputs[1])
    dab = N.new('ShaderNodeMath'); dab.operation = 'MULTIPLY'; dab.inputs[1].default_value = 6.0
    L.new(one_minus.outputs[0], dab.inputs[0]); L.new(dab.outputs[0], absorb.inputs['Density'])
    sct = N.new('ShaderNodeVolumeScatter'); sct.inputs['Color'].default_value = (0.97, 0.95, 0.90, 1)
    sct.inputs['Anisotropy'].default_value = 0.2
    dsc = N.new('ShaderNodeMath'); dsc.operation = 'MULTIPLY'; dsc.inputs[1].default_value = 60.0
    L.new(a.outputs[0], dsc.inputs[0]); L.new(dsc.outputs[0], sct.inputs['Density'])
    add = N.new('ShaderNodeAddShader'); L.new(absorb.outputs[0], add.inputs[0]); L.new(sct.outputs[0], add.inputs[1])
    L.new(add.outputs[0], out.inputs['Volume'])
    return m

def flat_coffee(level, mat):
    """Resting coffee: a closed cylinder (tucked 0.4 mm into the ceramic) with outward normals."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=R_IN + 0.04, depth=level + 0.05, location=(0, 0, (level - 0.05) / 2))
    ob = bpy.context.object; ob.name = 'coffee'
    from mathutils import Matrix
    ob.data.transform(Matrix.Translation((0, 0, (level - 0.05) / 2))); ob.location = (0, 0, 0)   # object z = world z
    for f in ob.data.polygons: f.use_smooth = len(f.vertices) == 4      # smooth sides, flat caps
    ob.data.materials.append(mat)
    return ob

def surface_mesh(alpha_rz, dr_cm, name='coffee'):
    """3D liquid surface (alpha = 0.5) of an axisymmetric field via marching cubes on a revolved voxel grid."""
    from skimage.measure import marching_cubes
    from scipy.ndimage import map_coordinates
    nz, nr = alpha_rz.shape
    vox = 0.05                                                    # cm
    xs = np.arange(-R_IN - 0.2, R_IN + 0.2 + vox, vox); zs = np.arange(-0.15, nz * dr_cm, vox)
    X, Y = np.meshgrid(xs, xs, indexing='ij')
    Rr = np.sqrt(X ** 2 + Y ** 2)
    ir = np.clip(Rr / dr_cm - 0.5, 0, nr - 1)
    vol = np.empty((len(xs), len(xs), len(zs)), np.float32)
    for k, z in enumerate(zs):
        iz = np.full_like(ir, np.clip(z / dr_cm - 0.5, 0, nz - 1))
        sl = map_coordinates(alpha_rz.astype(np.float32), [iz, ir], order=1)
        sl[Rr > R_IN + 0.04] = 0.0                                  # liquid tucked 0.4 mm into the ceramic wall
        vol[:, :, k] = sl
    vol[:, :, 0] = 0.0; vol[:, :, -1] = 0.0                       # close the surface at the bottom and top of the box
    verts, faces, _, _ = marching_cubes(vol, 0.5, spacing=(vox, vox, vox))
    verts += np.array([xs[0], xs[0], zs[0]])
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    if np.einsum('ij,ij->i', v0, np.cross(v1, v2)).sum() < 0:       # signed volume < 0: normals point inward, flip
        faces = faces[:, ::-1]
    me = bpy.data.meshes.new(name); me.from_pydata(verts.tolist(), [], faces.tolist())
    for f in me.polygons: f.use_smooth = True
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    return ob

def float_image(name, arr):
    nz, nr = arr.shape
    img = bpy.data.images.new(name, width=nr, height=nz, alpha=True, float_buffer=True)
    try: img.colorspace_settings.name = 'Non-Color'
    except Exception: pass
    set_image(img, arr); return img

def set_image(img, arr):
    a = np.clip(np.asarray(arr, np.float32), 0, None)
    rgba = np.stack([a, a, a, np.ones_like(a)], axis=-1)
    img.pixels.foreach_set(rgba.ravel()); img.update()

def steam_volume(level, img, rmax_cm, zmax_cm):
    m = bpy.data.materials.new('steam'); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
    for n in list(N): N.remove(n)
    tc = N.new('ShaderNodeTexCoord'); sep = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sep.inputs[0])
    cxy = N.new('ShaderNodeCombineXYZ'); L.new(sep.outputs[0], cxy.inputs[0]); L.new(sep.outputs[1], cxy.inputs[1])
    ln = N.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'; L.new(cxy.outputs[0], ln.inputs[0])
    u = N.new('ShaderNodeMath'); u.operation = 'DIVIDE'; L.new(ln.outputs['Value'], u.inputs[0]); u.inputs[1].default_value = rmax_cm
    v = N.new('ShaderNodeMath'); v.operation = 'MULTIPLY_ADD'; L.new(sep.outputs[2], v.inputs[0])
    v.inputs[1].default_value = 1 / zmax_cm; v.inputs[2].default_value = 0.5
    uv = N.new('ShaderNodeCombineXYZ'); L.new(u.outputs[0], uv.inputs[0]); L.new(v.outputs[0], uv.inputs[1])
    tx = N.new('ShaderNodeTexImage'); tx.image = img; tx.interpolation = 'Linear'; tx.extension = 'CLIP'
    L.new(uv.outputs[0], tx.inputs['Vector'])
    sepc = N.new('ShaderNodeSeparateColor'); L.new(tx.outputs['Color'], sepc.inputs[0])
    dens = N.new('ShaderNodeMath'); dens.operation = 'MULTIPLY'; dens.name = 'steamGain'; dens.inputs[1].default_value = 1.0
    L.new(sepc.outputs[0], dens.inputs[0])
    sc = N.new('ShaderNodeVolumeScatter'); sc.inputs['Color'].default_value = (1, 1, 1, 1); sc.inputs['Anisotropy'].default_value = 0.65
    L.new(dens.outputs[0], sc.inputs['Density'])
    out = N.new('ShaderNodeOutputMaterial'); L.new(sc.outputs[0], out.inputs['Volume'])
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=rmax_cm, depth=zmax_cm, location=(0, 0, level + zmax_cm / 2))
    ob = bpy.context.object; ob.name = 'steam'; ob.data.materials.append(m); ob.visible_shadow = False
    return ob, dens

def milk_stream(level, top):
    mat = principled('milk', (0.95, 0.93, 0.88), 0.25, **{'Subsurface Weight': 0.6})
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=0.26, radius2=0.42, depth=top - level, location=(0, 0, (top + level) / 2))
    ob = bpy.context.object; ob.data.materials.append(mat)
    for f in ob.data.polygons: f.use_smooth = True
    return ob

def camera(shot):
    cams = {  # location, target, lens, f-stop
        'establish': ((26, -62, 30), (-2, 0, 6.5), 50, 4.0),
        'pour':      ((12, -30, 26), (0, 0, 6.0), 60, 2.8),
        'milk':      ((9, -21, 21), (0, 0, 6.5), 60, 2.8),
    }
    loc, tgt, lens, fs = cams[shot]
    bpy.ops.object.camera_add(location=loc); cam = bpy.context.object; bpy.context.scene.camera = cam
    d = np.array(tgt) - np.array(loc)
    cam.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    cam.data.lens = lens; cam.data.dof.use_dof = True; cam.data.dof.focus_distance = float(np.linalg.norm(d))
    cam.data.dof.aperture_fstop = fs / 100;   # scene in cm cam.data.clip_start = 0.5; cam.data.clip_end = 2000

# ------------------------------------------------------------------ main
def render_shot(shot, frames, res_x, res_y, spp, out_fn):
    sc = setup(res_x, res_y, spp); build_room(); build_cup(); camera(shot)
    steam = load('steam'); pour = load('pour'); milk = load('milk3d')
    level_after = 7.5
    if pour is not None:
        last = pour['data'][-1].astype(np.float32); dr = float(pour['dr']) * 100
        col = last[:, :int(3.5 / dr)].mean(axis=1); level_after = float((col > 0.5).sum() * dr)
    level = {'establish': LEVEL0, 'pour': LEVEL0, 'milk': level_after}[shot]
    st_img = None
    if steam is not None:
        s_dr, s_rm, s_zm = float(steam['dr']) * 100, float(steam['rmax']) * 100, float(steam['zmax']) * 100
        st_img = float_image('steam', steam['data'][0].astype(np.float32))
        _, gain = steam_volume(level, st_img, s_rm, s_zm)
        # physical extinction of the condensed droplets: beta = 3 LWC / (2 rho_w r), LWC = rho_air * condensed mass fraction
        r_drop, rho_air, rho_w = 2e-6, 1.1, 1000.0
        gain.inputs[1].default_value = 1.5 * rho_air / (rho_w * r_drop) / 100.0      # per cm per unit mass fraction
    milk_img = float_image('milk', np.zeros(milk['data'].shape[1:], np.float32)) if shot == 'milk' and milk is not None else None
    mat = coffee_material(milk_img)
    liquid = None if shot == 'pour' else flat_coffee(level, mat)
    stream = milk_stream(level, level + 9.0) if shot == 'milk' else None
    for k in frames:
        t = k / FPS
        if st_img is not None:
            ts = STEAM_T0[shot] + t; i = int(np.argmin(np.abs(steam['t'] - ts)))
            set_image(st_img, steam['data'][i].astype(np.float32))
        if shot == 'pour' and pour is not None:
            if liquid is not None: bpy.data.objects.remove(liquid, do_unlink=True)
            i = int(np.argmin(np.abs(pour['t'] - t)))
            liquid = surface_mesh(pour['data'][i].astype(np.float32), float(pour['dr']) * 100); liquid.data.materials.append(mat)
        if shot == 'milk' and milk is not None:
            i = int(np.argmin(np.abs(milk['t'] - t))); set_image(milk_img, milk['data'][i].astype(np.float32))
            stream.hide_render = t > 1.22
        sc.render.filepath = out_fn(k); bpy.ops.render.render(write_still=True); print('rendered', shot, k, flush=True)

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'still':
        shot, k, rx, ry, spp, out = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
        render_shot(shot, [k], rx, ry, spp, lambda _: out)
    else:
        shot, rx, ry, spp, outdir = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
        first = int(sys.argv[7]) if len(sys.argv) > 7 else 0; last = int(sys.argv[8]) if len(sys.argv) > 8 else SHOTS[shot] - 1
        os.makedirs(outdir, exist_ok=True)
        render_shot(shot, range(first, last + 1), rx, ry, spp, lambda k: os.path.join(outdir, f'{shot}_{k:04d}.png'))
