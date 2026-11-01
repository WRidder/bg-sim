# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Independent design calculation of the two-span bridge on a centre pier (numpy only, no bg-sim code).

The bridge: one main truss of a 2 x 24 m continuous road bridge over a river, eight 6 m panels,
straight at the bottom (the deck) and haunched at the top (5 m deep at the first posts, 7 m over
the pier), a Pratt truss with a post at every inner panel point, inclined end posts, and **both**
diagonals in the two panels next to the pier (X-bracing). It stands on the two abutments and on
a 12 m steel column in the river. The deck and the lorry are shared equally by the two main
trusses (the convention of the Warren truss of ``design.py``, whose steel, deck mass per metre,
damping and lorry this bridge reuses). Node and bar numbering as in the model (`Truss2D`, the
deck polyline first):

    nodes  1      approach slab, far end (-40, 0), fixed
           2      approach slab at the abutment (-1, -0.06), fixed (settled 6 cm: the ramp)
           3..11  bottom chord at x = 0, 6, .., 48: 3 pinned, 7 on the pier column, 11 on a roller
           12     approach slab beyond the bridge (88, 0), fixed
           13..19 top chord at x = 6, .., 42, y = h(x) = 5 + 2 (1 - |x - 24| / 18)^2
           20     foot of the pier column (24, -12), pinned
    bars   1..8   bottom chord     9..14 top chord     15, 16 inclined end posts     17..23 posts
           24..31 diagonals (two in each panel next to the pier: 26, 27 left, 28, 29 right)
           32     the pier column (20 -> 7)

The truss is statically indeterminate (32 bars + 5 reactions - 2 x 17 joint equations = 3
redundants: the two X-braced panels and the pier), so the method of joints does not apply. This
script uses the stiffness method (assembled K, lumped M) and writes ``design_pier.json``:

* the lumped node masses (Truss2D: ``mn`` plus half of every bar meeting the node);
* the static member forces, reactions and deflections for the dead load and for the dead load
  plus a 100 kN point load at the middle of the left span;
* the eigenfrequencies of the linearised truss, with the first vertical bending mode (the two
  spans swing in opposite directions about the pier);
* the quasi-static envelope of every member under the two-axle lorry of 20 t and of 40 t;
* the slender diagonal of the failure model: in a redundant panel a bar's force follows its
  axial stiffness E A / L, not its I, so the diagonal keeps its area and only its buckling load
  is reduced: I = WEAK_RATIO x the design section's (a too slender strut). It holds the 20 t
  lorry quasi-statically and buckles under the 40 t one;
* the envelopes of the truss without that diagonal (after it has buckled): the redistribution.

    uv run examples/bridge/design/design_pier.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import design as w   # the Warren-truss design: the same steel, deck mass, damping and lorry

HERE = Path(__file__).resolve().parent

G0, E, RHO, FY, KEFF, BETA = w.G0, w.E, w.RHO, w.FY, w.KEFF, w.BETA
PANEL, NPANEL = 6.0, 8
SPAN = PANEL * NPANEL             # 48 m: two 24 m spans
H_END, H_PIER = 5.0, 7.0          # truss depth at the first posts and over the pier
PIER_H = 12.0                     # the column stands 12 m below the deck
DIP = w.DIP
M_DECK = w.M_DECK * PANEL / w.PANEL   # the Warren deck's mass per metre
TRUCK = w.TRUCK
P_STATIC = 100.0e3                # the static point load (N), at the middle of the left span
MODE_AMP = 0.005                  # bridge-pier-modes: start amplitude of the first mode at node LOAD_NODE (m)
# sections per truss: (area m^2, second moment m^4)
SEC = {
    "bottom": (1.6e-3, 8.0e-6),
    "top": (2.0e-3, 1.2e-5),
    "endpost": (2.0e-3, 1.6e-5),    # the inclined end posts
    "post": (1.4e-3, 4.0e-6),
    "pierpost": (2.4e-3, 1.6e-5),   # the post over the pier
    "diag": (1.4e-3, 1.0e-5),
    "pierdiag": (1.8e-3, 1.5e-5),   # the X-braced panels next to the pier
    "pier": (6.0e-3, 4.3e-5),
}
WEAK_RATIO = 0.35                 # the slender diagonal: I (and so Pcr) = 0.35 x the design section's

# node numbers (1-based, as in the model)
NB0 = 3                           # bottom chord: nodes 3 .. 3 + NPANEL at x = 0, 6, .., 48
ND = NB0 + NPANEL + 1             # the deck polyline: 1, 2, the bottom chord, the right approach
NT0 = ND + 1                      # top chord: x = 6 .. 42 (the end panels are triangles)
NTOP = NPANEL - 1
NODE_FOOT = NT0 + NTOP            # pier foot
NODE_PIER = NB0 + NPANEL // 2     # bottom node on the pier (x = 24)
NODE_ROLLER = NB0 + NPANEL        # x = 48
LOAD_NODE = NB0 + NPANEL // 4     # middle of the left span (x = 12)
RIGHT_NODE = NB0 + 3 * NPANEL // 4  # middle of the right span (x = 36)


def depth(x: float) -> float:
    return H_END + (H_PIER - H_END) * (1.0 - abs(x - SPAN / 2) / (SPAN / 2 - PANEL)) ** 2


def bottom(i: int) -> int:        # bottom node at x = PANEL i
    return NB0 + i


def top(i: int) -> int:           # top node at x = PANEL i, i = 1 .. NPANEL - 1
    return NT0 + i - 1


def geometry():
    xy = [(-40.0, 0.0), (-1.0, -DIP)]
    xy += [(PANEL * i, 0.0) for i in range(NPANEL + 1)]
    xy += [(SPAN + 40.0, 0.0)]
    xy += [(PANEL * i, depth(PANEL * i)) for i in range(1, NPANEL)]
    xy += [(SPAN / 2, -PIER_H)]
    xy = np.array(xy)
    bars, group = [], []
    for i in range(NPANEL):
        bars.append((bottom(i), bottom(i + 1))); group.append("bottom")
    for i in range(1, NPANEL - 1):
        bars.append((top(i), top(i + 1))); group.append("top")
    bars.append((bottom(0), top(1))); group.append("endpost")
    bars.append((top(NPANEL - 1), bottom(NPANEL))); group.append("endpost")
    for i in range(1, NPANEL):
        bars.append((bottom(i), top(i))); group.append("pierpost" if bottom(i) == NODE_PIER else "post")
    half = NPANEL // 2
    for p in range(1, NPANEL - 1):                 # the inner panels, from x = PANEL p to PANEL (p + 1)
        if p in (half - 1, half):                  # next to the pier: both diagonals
            bars.append((bottom(p), top(p + 1))); group.append("pierdiag")
            bars.append((top(p), bottom(p + 1))); group.append("pierdiag")
        elif p < half:                             # left span: down from the side of the nearer support
            bars.append((top(p), bottom(p + 1)) if p < half // 2 else (bottom(p), top(p + 1))); group.append("diag")
        else:
            q = NPANEL - 1 - p                     # the mirror image
            bars.append((bottom(p), top(p + 1)) if q < half // 2 else (top(p), bottom(p + 1))); group.append("diag")
    bars.append((NODE_FOOT, NODE_PIER)); group.append("pier")
    fix = np.zeros((len(xy), 2), dtype=int)
    fix[[0, 1, ND - 1], :] = 1                     # approach nodes
    fix[bottom(0) - 1, :] = 1                      # pinned bearing
    fix[NODE_ROLLER - 1, 1] = 1                    # roller bearing
    fix[NODE_FOOT - 1, :] = 1                      # pier foot, pinned
    A = np.array([SEC[g][0] for g in group])
    I = np.array([SEC[g][1] for g in group])
    mn = np.zeros(len(xy))
    mn[[bottom(i) - 1 for i in range(1, NPANEL)]] = M_DECK
    mn[[bottom(0) - 1, NODE_ROLLER - 1]] = M_DECK / 2
    mn[[0, 1, ND - 1, NODE_FOOT - 1]] = 1.0        # fixed: irrelevant
    return xy, np.array(bars), group, fix, A, I, mn


class Truss:
    """Linear stiffness model of the truss with the bars `active` (a failed bar is removed)."""

    def __init__(self, xy, bars, fix, A, active=None):
        self.xy, self.bars, self.fix, self.A = xy, bars, fix, A
        self.nn, self.nb = len(xy), len(bars)
        self.active = np.ones(self.nb, bool) if active is None else active
        self.L0 = np.array([np.linalg.norm(xy[b - 1] - xy[a - 1]) for a, b in bars])
        self.free = [2 * i + j for i in range(self.nn) for j in range(2) if fix[i, j] == 0]
        Ka = w.stiffness(xy, bars, np.where(self.active, A, 0.0))
        self.K = Ka[np.ix_(self.free, self.free)]
        self.B = w.equilibrium(xy, bars)

    def solve(self, F):
        """Displacements, member forces (tension +) and all nodal reactions under the loads F."""
        u = np.zeros(2 * self.nn)
        u[self.free] = np.linalg.solve(self.K, F[self.free])
        ext = -(self.B.T @ u)                   # B[:, k] = +n at a, -n at b: n.(u_b - u_a) = -B^T u
        N = np.where(self.active, E * self.A / self.L0 * ext, 0.0)
        return u, N, -(F + self.B @ N)


def main():
    xy, bars, group, fix, A, I, mn = geometry()
    nn, nb = len(xy), len(bars)
    m = w.lumped_masses(xy, bars, A, mn)
    tr = Truss(xy, bars, fix, A)
    L0 = tr.L0
    Ft = FY * A
    Pcr = np.pi ** 2 * E * I / (KEFF * L0) ** 2
    truss_nodes = nn - 3                                # all but the three approach-slab nodes
    assert len(tr.free) == 2 * truss_nodes - 5, len(tr.free)   # 5 reaction components
    redundants = nb + 5 - 2 * truss_nodes
    pier_bar = nb - 1                                   # 0-based index of the column: the last bar
    pier_post = next(k for k in range(nb) if group[k] == "pierpost")

    F_dead = w.node_loads(xy, m)
    u_dead, N_dead, R_dead = tr.solve(F_dead)
    F_static = w.node_loads(xy, m, {LOAD_NODE: -P_STATIC})
    u_static, N_static, R_static = tr.solve(F_static)
    # equilibrium: no residual at a free node, the reactions carry the whole weight and the load
    for R in (R_dead, R_static):
        assert np.allclose(R[tr.free], 0.0, atol=1e-6)
    weight = G0 * np.sum(m[[i for i in range(nn) if i not in (0, 1, ND - 1)]]) + P_STATIC
    b0, ro, ft = bottom(0), NODE_ROLLER, NODE_FOOT
    react = lambda R: {f"{b0}x": R[2 * b0 - 2], f"{b0}y": R[2 * b0 - 1], f"{ro}y": R[2 * ro - 1],
                       f"{ft}x": R[2 * ft - 2], f"{ft}y": R[2 * ft - 1]}
    Rd, Rs = react(R_dead), react(R_static)
    assert abs(Rs[f"{b0}y"] + Rs[f"{ro}y"] + Rs[f"{ft}y"] - weight) < 1e-6 * weight

    # eigenfrequencies (symmetric generalised problem by mass scaling)
    Mv = np.repeat(m, 2)[tr.free]
    Minv = 1 / np.sqrt(Mv)
    w2, V = np.linalg.eigh(Minv[:, None] * tr.K * Minv[None, :])
    freqs = np.sqrt(w2) / (2 * np.pi)
    full = np.zeros((2 * nn, len(tr.free)))
    full[tr.free, :] = Minv[:, None] * V
    vmid = full[2 * (LOAD_NODE - 1) + 1, :]
    first = int(np.argmax(np.abs(vmid) > 0.3 * np.max(np.abs(vmid))))
    phi = full[:, first] / full[2 * (LOAD_NODE - 1) + 1, first]
    phi_right = float(phi[2 * (RIGHT_NODE - 1) + 1])      # the right span's midpoint
    # kinetic energy at the start of bridge-pier-modes: velocity omega a phi, a = 5 mm at node LOAD_NODE
    Ek0 = 0.5 * (2 * np.pi * freqs[first] * MODE_AMP) ** 2 * float(np.sum(np.repeat(m, 2) * phi ** 2))

    # quasi-static lorry envelope (per truss: two axles of half the lorry each)
    positions = np.linspace(-5.0, SPAN + 5.0, 1301)

    def envelope(t: Truss, mass: float):
        axle = mass / 2 * G0 / 2
        _, N0, _ = t.solve(F_dead)
        Nmax, Nmin = N0.copy(), N0.copy()
        defl = np.zeros(nn)
        for s in positions:
            F = (w.shape_loads(xy, ND, s + TRUCK["wheelbase"] / 2, axle)
                 + w.shape_loads(xy, ND, s - TRUCK["wheelbase"] / 2, axle))
            u, N, _ = t.solve(F)
            Nmax = np.maximum(Nmax, N0 + N)
            Nmin = np.minimum(Nmin, N0 + N)
            defl = np.minimum(defl, u[1::2])
        return Nmax, Nmin, defl

    def utilisation(Nmax, Nmin, Pc):
        return np.maximum(Nmax / Ft, -Nmin / Pc)

    m20, m40 = TRUCK["m"], 2 * TRUCK["m"]
    Nmax, Nmin, defl = envelope(tr, m20)
    Nmax40, Nmin40, defl40 = envelope(tr, m40)
    # the slender diagonal: in the left span the diagonal with the largest compression
    xmid = lambda k: 0.5 * (xy[bars[k][0] - 1, 0] + xy[bars[k][1] - 1, 0])
    diag = [k for k in range(nb) if group[k] == "pierdiag" and xmid(k) < SPAN / 2]
    weak = min(diag, key=lambda k: Nmin[k])
    partner = next(k for k in diag if k != weak and abs(xmid(k) - xmid(weak)) < 1e-9)   # the X-partner
    I_weak = WEAK_RATIO * I[weak]
    Pcr_weak = WEAK_RATIO * Pcr[weak]
    Pcr_w = Pcr.copy()
    Pcr_w[weak] = Pcr_weak
    util, util40 = utilisation(Nmax, Nmin, Pcr), utilisation(Nmax40, Nmin40, Pcr)
    util_w, util40_w = utilisation(Nmax, Nmin, Pcr_w), utilisation(Nmax40, Nmin40, Pcr_w)
    # after the slender diagonal has buckled: the structure without it, under both lorries
    gone = np.ones(nb, bool)
    gone[weak] = False
    tg = Truss(xy, bars, fix, A, active=gone)
    Nmax_g, Nmin_g, defl_g = envelope(tg, m20)
    Nmax40_g, Nmin40_g, defl40_g = envelope(tg, m40)
    util_g, util40_g = utilisation(Nmax_g, Nmin_g, Pcr), utilisation(Nmax40_g, Nmin40_g, Pcr)
    util_g[weak] = util40_g[weak] = 0.0

    out = {
        "constants": {"E": E, "rho": RHO, "fy": FY, "K": KEFF, "g0": G0, "beta": BETA, "panel": PANEL,
                      "span": SPAN, "h_end": H_END, "h_pier": H_PIER, "pier_h": PIER_H, "dip": DIP, "nd": ND,
                      "load_node": LOAD_NODE, "right_node": RIGHT_NODE, "pier_node": NODE_PIER, "foot_node": NODE_FOOT,
                      "roller_node": NODE_ROLLER, "left_bearing": bottom(0), "pier_bar": pier_bar + 1,
                      "pier_post_bar": pier_post + 1, "redundants": redundants, "P_static": P_STATIC,
                      "weak_bar": weak + 1, "partner_bar": partner + 1, "weak_ratio": WEAK_RATIO},
        "truck": TRUCK, "sections": SEC, "group": group,
        "xy": xy.tolist(), "bars": bars.tolist(), "fix": fix.tolist(), "A": A.tolist(), "I": I.tolist(),
        "mn": mn.tolist(), "m_node": m.tolist(), "L0": L0.tolist(), "Ft": Ft.tolist(), "Pcr": Pcr.tolist(),
        "dead": {"N": N_dead.tolist(), "R": Rd, "ux": u_dead[0::2].tolist(), "uy": u_dead[1::2].tolist()},
        "static": {"N": N_static.tolist(), "R": Rs, "ux": u_static[0::2].tolist(), "uy": u_static[1::2].tolist(),
                   "load_uy": float(u_static[2 * (LOAD_NODE - 1) + 1])},
        "modes": {"f": freqs[:8].tolist(), "first_bending": first, "f1": float(freqs[first]),
                  "phi_x": phi[0::2].tolist(), "phi_y": phi[1::2].tolist(), "phi_right_mid": phi_right,
                  "amplitude": MODE_AMP, "Ek0": Ek0},
        "vehicle": {
            "N_max": Nmax.tolist(), "N_min": Nmin.tolist(), "util_max": util.tolist(), "uy_min": defl.tolist(),
            "N_max_40": Nmax40.tolist(), "N_min_40": Nmin40.tolist(), "util_max_40": util40.tolist(),
            "uy_min_40": defl40.tolist(),
            "weak_I": float(I_weak), "weak_Pcr": float(Pcr_weak),
            "weak_Elost": float(Pcr_weak ** 2 * L0[weak] / (2 * E * A[weak])),   # strain energy at buckling
            "weak_margin_20": float(Pcr_weak / -Nmin[weak]), "weak_margin_40": float(Pcr_weak / -Nmin40[weak]),
            "util_max_weak": util_w.tolist(), "util_max_40_weak": util40_w.tolist(),
            "failed": {"N_max": Nmax_g.tolist(), "N_min": Nmin_g.tolist(), "util_max": util_g.tolist(),
                       "N_max_40": Nmax40_g.tolist(), "N_min_40": Nmin40_g.tolist(), "util_max_40": util40_g.tolist(),
                       "uy_min": defl_g.tolist(), "uy_min_40": defl40_g.tolist()},
        },
        "total_mass": float(np.sum(m[[i for i in range(nn) if i not in (0, 1, ND - 1, NODE_FOOT - 1)]])),
    }
    (HERE / "design_pier.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"nodes {nn}, bars {nb}, free dofs {len(tr.free)}; truss mass per truss {out['total_mass']:.0f} kg")
    print(f"dead load: reactions {', '.join(f'{k} {v / 1e3:.3f} kN' for k, v in Rd.items())}")
    print(f"static (+{P_STATIC / 1e3:.0f} kN at node {LOAD_NODE}): reactions "
          f"{', '.join(f'{k} {v / 1e3:.3f} kN' for k, v in Rs.items())}; uy[{LOAD_NODE}] "
          f"{u_static[2 * (LOAD_NODE - 1) + 1] * 1e3:.4f} mm (dead alone {u_dead[2 * (LOAD_NODE - 1) + 1] * 1e3:.4f} mm)")
    print(f"total vertical load {weight / 1e3:.3f} kN")
    print("  bar group    nodes     L0     dead   static | 20 t envelope [kN]  util | 40 t util | slender bar gone: 20 t  40 t")
    for k in range(nb):
        print(f"  {k + 1:3d} {group[k]:8s} ({int(bars[k][0]):2d},{int(bars[k][1]):2d}) {L0[k]:5.2f} "
              f"{N_dead[k] / 1e3:8.2f} {N_static[k] / 1e3:8.2f} | [{Nmin[k] / 1e3:7.1f}, {Nmax[k] / 1e3:7.1f}] {util_w[k]:.3f}"
              f" | {util40_w[k]:.3f} | {util_g[k]:.3f} {util40_g[k]:.3f}")
    print(f"eigenfrequencies [Hz]: {np.round(freqs[:8], 4)}; first bending #{first}: {freqs[first]:.5f} Hz "
          f"(right midspan / left midspan {phi_right:+.3f})")
    print(f"slender diagonal bar {weak + 1} (partner {partner + 1}): I {I_weak:.4e} m^4 ({I_weak / I[weak]:.4f} of the design), "
          f"Pcr {Pcr_weak / 1e3:.2f} kN; quasi-static peak 20 t {Nmin[weak] / 1e3:.1f} kN, 40 t {Nmin40[weak] / 1e3:.1f} kN")
    print(f"partner bar {partner + 1}: intact 20 t [{Nmin[partner] / 1e3:.1f}, {Nmax[partner] / 1e3:.1f}] kN, 40 t "
          f"[{Nmin40[partner] / 1e3:.1f}, {Nmax40[partner] / 1e3:.1f}]; slender bar gone 20 t [{Nmin_g[partner] / 1e3:.1f}, "
          f"{Nmax_g[partner] / 1e3:.1f}], 40 t [{Nmin40_g[partner] / 1e3:.1f}, {Nmax40_g[partner] / 1e3:.1f}] kN; "
          f"Ft {Ft[partner] / 1e3:.1f} kN, Pcr {Pcr[partner] / 1e3:.1f} kN")
    for name, u in (("design 20 t", util), ("design 40 t", util40), ("slender 20 t", util_w), ("slender 40 t", util40_w),
                    ("gone 20 t", util_g), ("gone 40 t", util40_g)):
        order = np.argsort(-u)[:5]
        print(f"  {name}: largest util " + ", ".join(f"bar {k + 1} {u[k]:.3f}" for k in order))
    print(f"live deflection min (20 t): left mid {defl[LOAD_NODE - 1] * 1e3:.2f} mm, right mid {defl[RIGHT_NODE - 1] * 1e3:.2f} mm")
    print(f"redundants {redundants}; pier column bar {pier_bar + 1}, post over the pier bar {pier_post + 1}")


if __name__ == "__main__":
    main()
