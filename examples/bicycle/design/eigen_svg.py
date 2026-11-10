# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Print the SVG of the eigenvalues against the forward speed (the paper's figure 3) for the docs.

    uv run examples/bicycle/design/eigen_svg.py > eigen.svg

The output is pasted into the `@@ svg @project eigen` section of tools/example_docs/src/bicycle.md.
"""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, benchmark as b
W, H, L, R, T, B = 640, 400, 56, 20, 20, 44
x0, x1, y0, y1 = 0.0, 10.0, -10.0, 10.0
X = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R)
Y = lambda y: T + (y1 - y) / (y1 - y0) * (H - T - B)
vs = np.linspace(0, 10, 401)
ev = np.array([np.sort_complex(b.eigenvalues(v)) for v in vs])
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="sans-serif" font-size="12">',
       f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>']
t2 = b.load_table2()["special"]; vw, vc = t2["v_w"], t2["v_c"]
out.append(f'<rect x="{X(vw):.1f}" y="{T}" width="{X(vc)-X(vw):.1f}" height="{H-T-B}" fill="#e3f1e3"/>')
for gy in range(-10, 11, 2):
    out.append(f'<line x1="{L}" y1="{Y(gy):.1f}" x2="{W-R}" y2="{Y(gy):.1f}" stroke="{"#888" if gy == 0 else "#e4e4e4"}" stroke-width="1"/>')
    out.append(f'<text x="{L-6}" y="{Y(gy)+4:.1f}" text-anchor="end">{gy}</text>')
for gx in range(0, 11):
    out.append(f'<line x1="{X(gx):.1f}" y1="{T}" x2="{X(gx):.1f}" y2="{H-B}" stroke="#e4e4e4" stroke-width="1"/>')
    out.append(f'<text x="{X(gx):.1f}" y="{H-B+16}" text-anchor="middle">{gx}</text>')
out.append(f'<text x="{(L+W-R)/2:.0f}" y="{H-6}" text-anchor="middle">forward speed v [m/s]</text>')
out.append(f'<text x="14" y="{(T+H-B)/2:.0f}" text-anchor="middle" transform="rotate(-90 14 {(T+H-B)/2:.0f})">eigenvalue [1/s]</text>')
def path(xs, ys, color, dash=None, width=2):
    pts = []
    segs = []
    for v, y in zip(xs, ys):
        if np.isnan(y) or y < y0 - 1 or y > y1 + 1:
            if pts: segs.append(pts); pts = []
            continue
        pts.append(f"{X(v):.1f},{Y(np.clip(y, y0, y1)):.1f}")
    if pts: segs.append(pts)
    for s in segs:
        out.append(f'<polyline points="{" ".join(s)}" fill="none" stroke="{color}" stroke-width="{width}"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
re = np.sort(ev.real, axis=1)
for k in range(4):
    path(vs, re[:, k], "#1f5fa8")
im = np.max(ev.imag, axis=1); im[im < 1e-9] = np.nan
path(vs, im, "#c0392b", "6 4")
for v, lab in ((vw, "v_w = 4.29"), (vc, "v_c = 6.02")):
    out.append(f'<line x1="{X(v):.1f}" y1="{T}" x2="{X(v):.1f}" y2="{H-B}" stroke="#2e7d32" stroke-width="1.5" stroke-dasharray="3 3"/>')
out.append(f'<text x="{(X(vw)+X(vc))/2:.1f}" y="{T+16}" text-anchor="middle" fill="#2e7d32">self-stable</text>')
out.append(f'<text x="{X(vw)-4:.1f}" y="{H-B-6}" text-anchor="end" fill="#2e7d32">v_w 4.29</text>')
out.append(f'<text x="{X(vc)+4:.1f}" y="{H-B-6}" fill="#2e7d32">v_c 6.02</text>')
out.append(f'<text x="{X(8.3):.1f}" y="{Y(9.2):.1f}" fill="#c0392b">Im weave</text>')
out.append(f'<text x="{X(7.4):.1f}" y="{Y(-3.6):.1f}" fill="#1f5fa8">Re weave</text>')
out.append(f'<text x="{X(7.6):.1f}" y="{Y(1.0):.1f}" fill="#1f5fa8">capsize</text>')
out.append(f'<text x="{X(0.9):.1f}" y="{Y(-8.6):.1f}" fill="#1f5fa8">castering</text>')
# table 2 markers (weave real parts)
for row in b.load_table2()["weave"]:
    out.append(f'<circle cx="{X(row["v"]):.1f}" cy="{Y(row["re"]):.1f}" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>')
    out.append(f'<circle cx="{X(row["v"]):.1f}" cy="{Y(row["im"]):.1f}" r="3.5" fill="none" stroke="#000" stroke-width="1.2"/>')
out.append(f'<text x="{W-R-4}" y="{H-B-22}" text-anchor="end">circles: table 2 of Meijaard et al. 2007</text>')
out.append("</svg>")
print("\n".join(out))
