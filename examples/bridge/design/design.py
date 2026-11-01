# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Independent design calculation of the `bridge` example (numpy only, no bg-sim code).

The bridge is one of the two main trusses of a 30 m Warren truss road bridge (six 5 m panels,
4 m deep), with the deck and the vehicle shared equally by the two trusses. The node and bar
numbering is the model's (`Truss2D`): the deck polyline first, left to right.

    nodes  1      approach slab, far end (-40, 0), fixed
           2      approach slab at the abutment (-1, -0.06), fixed: the slab has settled 6 cm,
                  so a vehicle meets a short ramp onto the bridge (the dynamic excitation)
           3..9   bottom chord at x = 0, 5, .., 30 (3 pinned, 9 on a roller)
           10     approach slab beyond the bridge (70, 0), fixed
           11..16 top chord at x = 2.5, 7.5, .., 27.5, y = 4
    bars   1..6   bottom chord, 7..11 top chord, 12..23 diagonals (panel p: 3+p -> 11+p, 11+p -> 4+p)

This script computes, and writes to ``design.json``:

* the lumped node masses (Truss2D: ``mn`` plus half of every bar meeting the node);
* the static member forces by the method of joints (the truss is statically determinate:
  2 x 13 joint equations = 23 bars + 3 reactions), for the dead load alone and for the dead
  load plus a 100 kN point load at midspan, and the linear midspan deflection;
* the eigenfrequencies of the linearised truss (stiffness K, lumped mass M), with the first
  vertical bending mode;
* the quasi-static envelope of every member under the two-axle vehicle (influence lines,
  axle loads shared by the deck nodes through the linear shape functions), and from it the
  section of the deliberately undersized diagonal of the failure models;
* the starts of the dynamic models: the node displacements of the static dead-load state.

    uv run examples/bridge/design/design.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

G0 = 9.81
E, RHO, FY, KEFF = 2.1e11, 7850.0, 3.55e8, 1.0
PANEL, HEIGHT, NPANEL = 5.0, 4.0, 6
SPAN = PANEL * NPANEL
DIP = 0.06                      # settlement of the left approach slab at the abutment
# sections (per truss): bottom chord, top chord, diagonals
A_BOT, I_BOT = 3.0e-3, 1.5e-5
A_TOP, I_TOP = 4.0e-3, 3.0e-5
A_DIA, I_DIA = 2.0e-3, 6.0e-6
WEAK_BAR = 13                   # the second diagonal from the left (tension under traffic)
WEAK_FACTOR = 1.4               # its strength: 1.4 x the quasi-static peak force of the 20 t lorry
M_DECK = 2500.0                 # deck mass per interior bottom node and truss (kg)
BETA = 1.0e-3                   # stiffness-proportional damping time of the bars (s)
# the vehicle (a 2-axle lorry; per truss: half of it)
TRUCK = {
    "m": 20000.0,               # total mass (kg); each truss carries half
    "wheelbase": 4.0,
    "J": 20000.0 * (8.0 ** 2 + 2.5 ** 2) / 12.0,   # pitch inertia of an 8 m x 2.5 m box
    "r": 0.5, "ry": -1.0,       # wheel radius, wheel centres 1 m below the centre of mass
    "k": 1.5e6, "c": 2.0e4,     # tyre stiffness and damping per wheel (per truss: one wheel per axle)
    "tau": 0.5,                 # speed controller time constant (s)
}
P_STATIC = 100.0e3              # point load of the static model at midspan (N)


def geometry():
    xy = [(-40.0, 0.0), (-1.0, -DIP)]
    xy += [(PANEL * i, 0.0) for i in range(NPANEL + 1)]
    xy += [(70.0, 0.0)]
    xy += [(PANEL * (i + 0.5), HEIGHT) for i in range(NPANEL)]
    xy = np.array(xy)
    bars = [(3 + i, 4 + i) for i in range(NPANEL)]                    # bottom chord
    bars += [(11 + i, 12 + i) for i in range(NPANEL - 1)]             # top chord
    for p in range(NPANEL):
        bars += [(3 + p, 11 + p), (11 + p, 4 + p)]                     # diagonals
    fix = np.zeros((len(xy), 2), dtype=int)
    fix[[0, 1, 9], :] = 1                                              # approach nodes
    fix[2, :] = 1                                                      # pinned bearing
    fix[8, 1] = 1                                                      # roller bearing
    A = np.array([A_BOT] * 6 + [A_TOP] * 5 + [A_DIA] * 12)
    I = np.array([I_BOT] * 6 + [I_TOP] * 5 + [I_DIA] * 12)
    mn = np.zeros(len(xy))
    mn[3:8] = M_DECK
    mn[[2, 8]] = M_DECK / 2
    mn[[0, 1, 9]] = 1.0                                                # fixed: the mass is irrelevant
    return xy, np.array(bars), fix, A, I, mn


def lumped_masses(xy, bars, A, mn):
    m = mn.copy()
    for k, (a, b) in enumerate(bars):
        L0 = np.linalg.norm(xy[b - 1] - xy[a - 1])
        m[a - 1] += 0.5 * RHO * A[k] * L0
        m[b - 1] += 0.5 * RHO * A[k] * L0
    return m


def free_dofs(fix):
    return [2 * i + j for i in range(fix.shape[0]) for j in range(2) if fix[i, j] == 0]


def equilibrium(xy, bars):
    """B (2 nn x nb): the nodal force of a unit tension in every bar (+n on node a, -n on b)."""
    B = np.zeros((2 * len(xy), len(bars)))
    for k, (a, b) in enumerate(bars):
        d = xy[b - 1] - xy[a - 1]
        n = d / np.linalg.norm(d)
        B[2 * (a - 1):2 * a, k] += n
        B[2 * (b - 1):2 * b, k] -= n
    return B


def stiffness(xy, bars, A):
    K = np.zeros((2 * len(xy), 2 * len(xy)))
    for k, (a, b) in enumerate(bars):
        d = xy[b - 1] - xy[a - 1]
        L = np.linalg.norm(d)
        n = d / L
        kk = E * A[k] / L * np.outer(n, n)
        ia, ib = slice(2 * (a - 1), 2 * a), slice(2 * (b - 1), 2 * b)
        K[ia, ia] += kk
        K[ib, ib] += kk
        K[ia, ib] -= kk
        K[ib, ia] -= kk
    return K


def method_of_joints(xy, bars, fix, F):
    """Member forces N (tension +) and reactions from the joint equilibrium B N + F + R = 0."""
    B = equilibrium(xy, bars)
    truss_nodes = sorted({int(i) for bar in bars for i in bar})
    rows = [2 * (i - 1) + j for i in truss_nodes for j in range(2)]
    reaction_rows = [r for r in rows if fix[r // 2, r % 2] == 1]
    # unknowns: N (nb) and the reactions at the fixed bearing components
    Mx = np.zeros((len(rows), len(bars) + len(reaction_rows)))
    Mx[:, :len(bars)] = B[rows, :]
    for j, r in enumerate(reaction_rows):
        Mx[rows.index(r), len(bars) + j] = 1.0
    assert Mx.shape[0] == Mx.shape[1], Mx.shape
    sol = np.linalg.solve(Mx, -F[rows])
    N = sol[:len(bars)]
    R = {f"{r // 2 + 1}{'xy'[r % 2]}": float(v) for r, v in zip(reaction_rows, sol[len(bars):])}
    return N, R


def node_loads(xy, m, extra=None):
    F = np.zeros(2 * len(xy))
    F[1::2] = -G0 * m
    if extra:
        for node, fy in extra.items():
            F[2 * (node - 1) + 1] += fy
    return F


def shape_loads(xy, nd, s, P):
    """Vertical load P (down) at deck abscissa s, shared by the two nodes of its panel."""
    F = np.zeros(2 * len(xy))
    xs = xy[:nd, 0]
    for j in range(nd - 1):
        if xs[j] <= s < xs[j + 1]:
            xi = (s - xs[j]) / (xs[j + 1] - xs[j])
            F[2 * j + 1] -= P * (1 - xi)
            F[2 * (j + 1) + 1] -= P * xi
    return F


def main():
    xy, bars, fix, A, I, mn = geometry()
    nn, nb, nd = len(xy), len(bars), 10
    m = lumped_masses(xy, bars, A, mn)
    L0 = np.array([np.linalg.norm(xy[b - 1] - xy[a - 1]) for a, b in bars])
    Ft = FY * A
    Pcr = np.pi ** 2 * E * I / (KEFF * L0) ** 2
    free = free_dofs(fix)
    K = stiffness(xy, bars, A)[np.ix_(free, free)]
    Mv = np.repeat(m, 2)[free]

    def solve(F):
        u = np.zeros(2 * nn)
        u[free] = np.linalg.solve(K, F[free])
        return u

    mid = 6                                                      # bottom node at x = 15
    F_dead = node_loads(xy, m)
    N_dead, R_dead = method_of_joints(xy, bars, fix, F_dead)
    u_dead = solve(F_dead)
    F_static = node_loads(xy, m, {mid: -P_STATIC})
    N_static, R_static = method_of_joints(xy, bars, fix, F_static)
    u_static = solve(F_static)
    # the linear solve must give the same member forces (a determinate truss)
    B = equilibrium(xy, bars)
    N_check = np.array([E * A[k] / L0[k] * (B[:, k] @ u_static) * -1 for k in range(nb)])
    assert np.allclose(N_check, N_static, rtol=1e-8, atol=1e-6), np.max(np.abs(N_check - N_static))

    # eigenfrequencies (symmetric generalised problem by mass scaling)
    Minv = 1 / np.sqrt(Mv)
    w2, V = np.linalg.eigh(Minv[:, None] * K * Minv[None, :])
    freqs = np.sqrt(w2) / (2 * np.pi)
    modes = Minv[:, None] * V
    full = np.zeros((2 * nn, len(free)))
    full[free, :] = modes
    # the first mode with a sizeable midspan vertical component: the first bending mode
    vmid = full[2 * (mid - 1) + 1, :]
    first = int(np.argmax(np.abs(vmid) > 0.3 * np.max(np.abs(vmid))))
    phi = full[:, first] / full[2 * (mid - 1) + 1, first]    # midspan vertical = 1

    # quasi-static envelope under the vehicle (per truss: two axles, half the lorry each)
    m_truck = TRUCK["m"] / 2
    axle = m_truck * G0 / 2
    envelope = {"max": N_dead.copy(), "min": N_dead.copy()}
    defl = 0.0
    for s in np.linspace(-5.0, SPAN + 5.0, 1401):
        F = shape_loads(xy, nd, s + TRUCK["wheelbase"] / 2, axle) + shape_loads(xy, nd, s - TRUCK["wheelbase"] / 2, axle)
        N_live, _ = method_of_joints(xy, bars, fix, F)
        envelope["max"] = np.maximum(envelope["max"], N_dead + N_live)
        envelope["min"] = np.minimum(envelope["min"], N_dead + N_live)
        defl = min(defl, solve(F)[2 * (mid - 1) + 1])
    util_max = np.maximum(envelope["max"] / Ft, -envelope["min"] / Pcr)
    weak = WEAK_BAR - 1
    # the undersized diagonal: Ft just above the quasi-static peak of the design lorry
    weak_area = float(WEAK_FACTOR * envelope["max"][weak] / FY)

    out = {
        "constants": {"E": E, "rho": RHO, "fy": FY, "K": KEFF, "g0": G0, "beta": BETA,
                      "panel": PANEL, "height": HEIGHT, "span": SPAN, "dip": DIP, "nd": nd,
                      "weak_bar": WEAK_BAR, "mid_node": mid, "P_static": P_STATIC},
        "truck": TRUCK,
        "xy": xy.tolist(), "bars": bars.tolist(), "fix": fix.tolist(), "A": A.tolist(), "I": I.tolist(),
        "mn": mn.tolist(), "m_node": m.tolist(), "L0": L0.tolist(), "Ft": Ft.tolist(), "Pcr": Pcr.tolist(),
        "dead": {"N": N_dead.tolist(), "R": R_dead, "ux": u_dead[0::2].tolist(), "uy": u_dead[1::2].tolist()},
        "static": {"N": N_static.tolist(), "R": R_static, "ux": u_static[0::2].tolist(),
                   "uy": u_static[1::2].tolist(), "mid_uy": float(u_static[2 * (mid - 1) + 1]),
                   "util": [float(N_static[k] / Ft[k] if N_static[k] > 0 else N_static[k] / Pcr[k]) for k in range(nb)]},
        "modes": {"f": freqs[:6].tolist(), "first_bending": first, "f1": float(freqs[first]),
                  "phi_x": phi[0::2].tolist(), "phi_y": phi[1::2].tolist()},
        "vehicle": {"axle_load": axle, "N_max": envelope["max"].tolist(), "N_min": envelope["min"].tolist(),
                    "util_max": util_max.tolist(), "mid_uy_live_min": float(defl), "weak_area": weak_area,
                    "weak_Ft": FY * weak_area},
        "total_mass": float(np.sum(m[[i for i in range(nn) if i not in (0, 1, 9)]])),
    }
    (HERE / "design.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"node masses: {np.round(m, 1)}")
    print(f"dead load: reactions {R_dead}; midspan uy {u_dead[2 * (mid - 1) + 1]:.6f} m")
    print(f"static (+{P_STATIC / 1e3:.0f} kN at midspan): midspan uy {u_static[2 * (mid - 1) + 1]:.6f} m")
    for k in range(nb):
        print(f"  bar {k + 1:2d} ({int(bars[k][0])}, {int(bars[k][1])}): N_dead {N_dead[k] / 1e3:9.2f} kN  N_static {N_static[k] / 1e3:9.2f} kN"
              f"  envelope [{envelope['min'][k] / 1e3:8.1f}, {envelope['max'][k] / 1e3:8.1f}] kN  util_max {util_max[k]:.3f}")
    print(f"eigenfrequencies [Hz]: {np.round(freqs[:6], 4)}; first bending mode #{first}: {freqs[first]:.5f} Hz")
    print(f"weak diagonal (bar {WEAK_BAR}): area {weak_area:.4e} m^2, Ft {FY * weak_area / 1e3:.1f} kN"
          f" (quasi-static peak {envelope['max'][weak] / 1e3:.1f} kN)")
    print(f"live midspan deflection (quasi-static) {defl * 1e3:.2f} mm")


if __name__ == "__main__":
    main()
