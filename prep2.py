"""Prepare simulation output for the v2 Blender scene.

  pour : copies the per-frame iso-surface STLs (alpha.coffee = 0.5) to seq2/pour/NNNN.stl
  milk : from the 3D cell data -> (a) the colour of the coffee surface seen from above (milk fraction averaged over
         the top few mm, weighted by depth, Kubelka-Munk mixing) on a 256x256 (x, y) grid, and
         (b) the cross-section through the pour plane y = 0 on a (z, x) grid, also Kubelka-Munk coloured.
Colours are linear RGB reflectances.
"""
import os, re, sys, glob, shutil, numpy as np
from scipy.spatial import Delaunay
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

D = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(D, 'seq2'); os.makedirs(OUT, exist_ok=True)
what = sys.argv[1:] or ['pour', 'milk']

def read(path):
    txt = open(path).read()
    m = re.search(r'internalField\s+uniform\s+([-\d.eE+]+)', txt)
    if m: return float(m.group(1))
    m = re.search(r'internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\(', txt)
    n = int(m.group(1)); return np.array(txt[m.end():].split(None, n)[:n], float)

def to_lin(c): c = np.asarray(c, float); return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
R_coffee, R_milk = to_lin([0.21, 0.11, 0.055]), to_lin([0.97, 0.955, 0.92])
S_c, S_m = 0.02, 1.0
K_c = S_c * (1 - R_coffee) ** 2 / (2 * R_coffee); K_m = S_m * (1 - R_milk) ** 2 / (2 * R_milk)
def km(a):
    a = np.clip(a, 0, 1)[..., None]
    K = a * K_m + (1 - a) * K_c; S = a * S_m + (1 - a) * S_c; q = K / S
    return 1 + q - np.sqrt(q * q + 2 * q)

if 'pour' in what:
    case = os.path.join(D, 'pour3d'); dst = os.path.join(OUT, 'pour'); shutil.rmtree(dst, ignore_errors=True); os.makedirs(dst)
    times = sorted([t for t in os.listdir(os.path.join(case, 'postProcessing', 'liquidSurface'))], key=float)
    ts = []
    for i, t in enumerate(times):
        f = glob.glob(os.path.join(case, 'postProcessing', 'liquidSurface', t, '*.stl'))
        if f: shutil.copy(f[0], os.path.join(dst, f'{len(ts):04d}.stl')); ts.append(float(t))
    np.save(os.path.join(dst, 't.npy'), np.array(ts)); print('pour frames', len(ts))

if 'milk' in what:
    case = os.path.join(D, 'milk3d'); H = 0.066
    x, y, z = (read(os.path.join(case, '0', c)) for c in ('Cx', 'Cy', 'Cz'))
    P = np.column_stack([x, y, z]); tri = Delaunay(P)
    # top view: 256 x 256 over the mug opening, 6 depth layers within 6 mm of the surface
    g = np.linspace(-0.040, 0.040, 256); GX, GY = np.meshgrid(g, g)
    depths = np.array([0.4, 1.2, 2.0, 3.0, 4.5, 6.0]) * 1e-3; w = np.exp(-depths / 2.0e-3); w /= w.sum()
    inside = GX ** 2 + GY ** 2 < 0.0399 ** 2
    topP = np.concatenate([np.column_stack([GX[inside], GY[inside], np.full(inside.sum(), H - d)]) for d in depths])
    # cross-section y = 0: (z, x)
    sx = np.linspace(-0.040, 0.040, 256); sz = np.linspace(0.0, H, 212); SX, SZ = np.meshgrid(sx, sz)
    secP = np.column_stack([SX.ravel(), np.zeros(SX.size), SZ.ravel()])
    times = sorted([t for t in os.listdir(case) if re.fullmatch(r'[\d.eE+-]+', t) and float(t) > 0
                    and os.path.exists(os.path.join(case, t, 'alpha.milk'))], key=float)
    tops, secs, amean = [], [], []
    for t in times:
        a = read(os.path.join(case, t, 'alpha.milk')); a = np.full(len(x), a) if np.isscalar(a) else a
        f = LinearNDInterpolator(tri, a); fn = NearestNDInterpolator(P, a)
        v = f(topP); v = np.where(np.isnan(v), fn(topP), v).reshape(len(depths), -1)
        aeff = np.zeros(GX.shape); aeff[inside] = (w[:, None] * v).sum(0)
        top = np.zeros(GX.shape + (3,)); top[inside] = km(aeff[inside]); tops.append(top.astype(np.float16))
        s = f(secP); s = np.where(np.isnan(s), fn(secP), s).reshape(SX.shape)
        secs.append(km(s).astype(np.float16)); amean.append(float(a.mean()))
    np.savez_compressed(os.path.join(OUT, 'milk.npz'), top=np.stack(tops), sec=np.stack(secs), t=np.array([float(t) for t in times]),
                        sec_x=sx, sec_z=sz, top_g=g, H=H, info='linear RGB reflectance (Kubelka-Munk); top: (frame, y, x); sec: (frame, z, x) at y=0')
    print('milk frames', len(times), 'mean milk fraction last', amean[-1])
