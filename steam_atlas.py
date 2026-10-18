"""Convert the 3D steam simulation into per-frame 'slice atlases' for Blender (no OpenVDB needed).

Voxel box (m): x [-0.06, 0.09], y [-0.075, 0.075], z [0, 0.28] at 3 mm -> 50 x 50 x 94 voxels; slice k sits in
tile (col = k % 10, row = k // 10) of a 500 x 500 image. Value: condensed water mass fraction at local
equilibrium, including the latent heat released (same as export_seq.py).
    python steam_atlas.py              -> seq2/steam_atlas.npz  (frames, 500, 500) float16 + times
"""
import os, re, numpy as np
from scipy.spatial import cKDTree
D = os.path.dirname(os.path.abspath(__file__)); CASE = os.path.join(D, 'steam3d')
BOX = ((-0.06, 0.09), (-0.075, 0.075), (0.0, 0.28)); N = (50, 50, 94); COLS = 10

def read_field(path):
    raw = open(path, 'rb').read()
    m = re.search(rb'internalField\s+uniform\s+([-\d.eE+]+)', raw[:4000])
    if m: return float(m.group(1))
    m = re.search(rb'internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\(', raw)
    n = int(m.group(1)); start = m.end()
    if re.search(rb'format\s+binary', raw[:2000]): return np.frombuffer(raw[start:start + 8 * n], dtype='<f8')
    return np.array(raw[start:].split(None, n)[:n], float)

def psat(T): Tc = T - 273.15; return 611.21 * np.exp((18.678 - Tc / 234.5) * (Tc / (257.14 + Tc)))
def ysat(T, p=101325.0): pv = psat(T); return 0.622 * pv / (p - 0.378 * pv)
def fog(Y, T, p=101325.0, L=2.4e6, cp=1010.0):
    sup = Y > ysat(T, p); lo, hi = T.copy(), T + 60.0
    for _ in range(40):
        mid = 0.5 * (lo + hi); f = cp * (mid - T) - L * (Y - ysat(mid, p))
        hi = np.where(f > 0, mid, hi); lo = np.where(f > 0, lo, mid)
    return np.where(sup, np.clip(Y - ysat(0.5 * (lo + hi), p), 0, None), 0.0)

cx, cy, cz = (read_field(os.path.join(CASE, '0', c)) for c in ('Cx', 'Cy', 'Cz'))
gx, gy, gz = (np.linspace(b[0], b[1], n) for b, n in zip(BOX, N))
X, Y, Z = np.meshgrid(gx, gy, gz, indexing='ij')                    # (nx, ny, nz)
P = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
dist, idx = cKDTree(np.column_stack([cx, cy, cz])).query(P, k=4)
w = 1.0 / np.maximum(dist, 1e-5) ** 2; w /= w.sum(1, keepdims=True)
far = dist[:, 0] > 0.006                                            # outside the fluid (inside the ceramic, etc.)

times = sorted([t for t in os.listdir(CASE) if re.fullmatch(r'[\d.eE+-]+', t) and float(t) > 0
                and os.path.exists(os.path.join(CASE, t, 'H2O'))], key=float)
atlases = []
for t in times:
    f = fog(read_field(os.path.join(CASE, t, 'H2O')), read_field(os.path.join(CASE, t, 'T')))
    v = (f[idx] * w).sum(1); v[far] = 0.0
    vol = v.reshape(N)                                              # (nx, ny, nz)
    rows = int(np.ceil(N[2] / COLS)); atlas = np.zeros((rows * N[1], COLS * N[0]), np.float32)
    for k in range(N[2]):
        r, c = divmod(k, COLS)
        atlas[r * N[1]:(r + 1) * N[1], c * N[0]:(c + 1) * N[0]] = vol[:, :, k].T   # image rows = y, columns = x
    atlases.append(atlas.astype(np.float16))
np.savez_compressed(os.path.join(D, 'seq2', 'steam_atlas.npz'), atlas=np.stack(atlases), t=np.array([float(t) for t in times]),
                    box=np.array(BOX), n=np.array(N), cols=COLS)
print('steam atlas frames', len(times), 'max', float(np.max([a.max() for a in atlases])))
