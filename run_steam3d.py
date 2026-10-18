"""Drive the 3D steam simulation through the whole film, one-way coupled to the cached pour.

Film physical time: 0-2.5 s empty mug | 2.5-7.1 s pour (pour simulation time 0-4.6 s) | 7.1-11.1 s milk shot.
Before each segment the cellZone 'coffee' is rebuilt from the pour result at that time: a cylinder up to the
current liquid level plus the falling stream (traced slab by slab from cells with alpha > 0.5).
    python run_steam3d.py            (needs pour3d reconstructed + cell centres; steam3d meshed)
"""
import os, re, subprocess, sys, numpy as np
D = os.path.dirname(os.path.abspath(__file__))
POUR, STEAM = os.path.join(D, 'pour3d'), os.path.join(D, 'steam3d')
T_POUR0, POUR_END, FILM_END, SEG = 2.5, 4.6, 11.1, 1 / 6
R_IN = 0.0402

def foam(cmd, case, log):
    full = f'source {os.environ.get("OF_ENV", "/usr/lib/openfoam/openfoam2412/etc/bashrc")}; cd {case}; {cmd} > {log} 2>&1'
    r = subprocess.run(['bash', '-c', full])
    if r.returncode: sys.exit(f'failed: {cmd} (see {case}/{log})')

def read_field(path):
    raw = open(path, 'rb').read()
    head = raw[:4000].decode('latin1')
    m = re.search(r'internalField\s+uniform\s+([-\d.eE+]+)', head)
    if m: return float(m.group(1))
    m = re.search(rb'internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\(', raw)
    n = int(m.group(1)); start = m.end()
    if b'format      binary' in raw[:2000] or b'format binary' in raw[:2000] or re.search(rb'format\s+binary', raw[:2000]):
        return np.frombuffer(raw[start:start + 8 * n], dtype='<f8')
    return np.array(raw[start:].split(None, n)[:n], float)

def pour_state():
    """List of (pour time, level, stream polyline [(x, y, z, r)])."""
    cx, cy, cz = (read_field(os.path.join(POUR, '0', c)) for c in ('Cx', 'Cy', 'Cz'))
    vol = read_field(os.path.join(POUR, '0', 'V'))
    rr = np.hypot(cx, cy); inside = (rr < 0.038) & (cz < 0.085)
    times = sorted([t for t in os.listdir(POUR) if re.fullmatch(r'[\d.eE+-]+', t) and float(t) > 0
                    and os.path.exists(os.path.join(POUR, t, 'alpha.coffee'))], key=float)
    out = []
    for t in times:
        a = read_field(os.path.join(POUR, t, 'alpha.coffee'))
        # level: lowest 2 mm slab inside the cup whose volume-weighted alpha drops below 0.5
        level = 0.0
        for z0 in np.arange(0.0, 0.085, 0.002):
            s = inside & (cz >= z0) & (cz < z0 + 0.002)
            if s.sum() == 0: continue
            if (a[s] * vol[s]).sum() / vol[s].sum() < 0.5: break
            level = z0 + 0.002
        pts = []
        for z0 in np.arange(level + 0.003, 0.131, 0.005):
            s = (a > 0.5) & (cz >= z0) & (cz < z0 + 0.005)
            if s.sum() == 0: continue
            w = vol[s]; area = w.sum() / 0.005
            pts.append((float((cx[s] * w).sum() / w.sum()), float((cy[s] * w).sum() / w.sum()), z0 + 0.0025, max(0.003, float(np.sqrt(area / np.pi)))))
        out.append((float(t), level, pts))
    return out

def zone_dict(level, pts):
    acts = []
    if level > 0.001:
        acts.append(f"{{ name coffeeSet; type cellSet; action new; source cylinderToCell; p1 (0 0 -0.01); p2 (0 0 {level:.5f}); radius {R_IN}; }}")
    else:
        acts.append("{ name coffeeSet; type cellSet; action new; source cylinderToCell; p1 (0 0 -0.006); p2 (0 0 -0.0059); radius 0.001; }")
    for (x0, y0, z0, r0), (x1, y1, z1, r1) in zip(pts[:-1], pts[1:]):
        acts.append(f"{{ name coffeeSet; type cellSet; action add; source cylinderToCell; p1 ({x0:.5f} {y0:.5f} {z0:.5f}); "
                    f"p2 ({x1:.5f} {y1:.5f} {z1:.5f}); radius {0.5 * (r0 + r1):.5f}; }}")
    acts.append("{ name coffee; type cellZoneSet; action new; source setToCellZone; set coffeeSet; }")
    return "FoamFile { version 2.0; format ascii; class dictionary; object topoSetDict; }\nactions\n(\n    " + "\n    ".join(acts) + "\n);\n"

def run_to(t_end, level, pts, k):
    open(os.path.join(STEAM, 'system', 'topoSetDict.seg'), 'w').write(zone_dict(level, pts))
    foam('mpirun -np 2 topoSet -parallel -dict system/topoSetDict.seg', STEAM, f'log.topo{k:03d}')
    foam(f'foamDictionary -entry endTime -set {t_end:.6f} system/controlDict', STEAM, 'log.dict')
    foam('mpirun -np 2 rhoReactingBuoyantFoam -parallel', STEAM, f'log.run{k:03d}')
    print(f'segment {k}: to t = {t_end:.3f} s, level {level * 100:.2f} cm, stream points {len(pts)}', flush=True)

if __name__ == '__main__':
    states = pour_state()
    levels = np.array([s[1] for s in states]); tp = np.array([s[0] for s in states])
    np.savetxt(os.path.join(D, 'pour_level.txt'), np.column_stack([tp, levels]), header='pour time [s], level [m]')
    k = 0
    run_to(T_POUR0, 0.0, [], k); k += 1                               # empty mug
    t = T_POUR0
    while t < T_POUR0 + POUR_END - 1e-9:
        i = int(np.argmin(np.abs(tp - (t - T_POUR0))))
        t_next = min(t + SEG, T_POUR0 + POUR_END)
        run_to(t_next, states[i][1], states[i][2], k); k += 1; t = t_next
    run_to(FILM_END, states[-1][1], [], k)                           # full mug, no stream
    print('STEAM3D_DONE', flush=True)
