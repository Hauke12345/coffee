"""Join the rendered v2 shots into one film (H.264, 24 fps). Frames may be every STEP-th frame (fast preview).
    python make_film2.py FRAMES_DIR OUT.mp4 [STEP] [WIDTH]
"""
import os, shutil, subprocess, sys
frames, out = sys.argv[1], sys.argv[2]; step = int(sys.argv[3]) if len(sys.argv) > 3 else 1
width = int(sys.argv[4]) if len(sys.argv) > 4 else 1920
try:
    import imageio_ffmpeg; ff = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    ff = shutil.which('ffmpeg') or sys.exit('need ffmpeg: pip install imageio-ffmpeg')
shots = [('establish', 60), ('pour', 110), ('milk', 96), ('cross', 96)]
fps_in = 24 / step; fade = 0.5
if any(f.startswith('film_') for f in os.listdir(frames)):      # continuous take (scene2.py film): no cuts, no crossfades
    subprocess.run([ff, '-y', '-loglevel', 'error', '-framerate', f'{fps_in}', '-start_number', '0', '-i', os.path.join(frames, 'film_%04d.png'),   # glob patterns are unsupported on Windows
                    '-vf', f'scale={width}:-2,setsar=1,format=yuv420p,fps=24', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], check=True)
    sys.exit(print('film:', out))
inputs, chains, durs = [], [], []
for i, (s, n) in enumerate(shots):
    inputs += ['-framerate', f'{fps_in}', '-pattern_type', 'glob', '-i', os.path.join(frames, f'{s}_*.png')]
    chains.append(f'[{i}:v]scale={width}:-2,setsar=1,format=yuv420p,fps=24[v{i}]'); durs.append(n / 24)
cur, prev = durs[0], 'v0'
for i in range(1, len(shots)):
    off = cur - fade; tag = f'x{i}' if i < len(shots) - 1 else 'out'
    chains.append(f'[{prev}][v{i}]xfade=transition=fade:duration={fade}:offset={off:.3f}[{tag}]'); cur = off + durs[i]; prev = tag
subprocess.run([ff, '-y', '-loglevel', 'error'] + inputs + ['-filter_complex', ';'.join(chains), '-map', '[out]', '-c:v', 'libx264',
                '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], check=True)
print('film:', out, f'{cur:.1f} s')
