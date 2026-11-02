# Robust classical control

Items C1 to C3 of `plan/ROBUST_CLASSICAL_PLAN.md`, run in bgsim by
[-robust](model:pendulum-double-cart-lab-robust) and [-recover](model:pendulum-double-cart-lab-recover).

**C1, robust balance** (`design/robust_c1.py`). Every law has the firmware structure
$u = -K\,[\hat x;\ u_{k-1};\ u_{k-2}]$ (8 gains) on the 1 kHz EKF and is designed with the 2-sample delay, the
armature lag and the observer in the loop. Four designs over 256 box corners and 64 draws: the multi-model
LQR (mean H2), structured H∞, μ-synthesis by D-K iteration, and Glover-McFarlane loop shaping. Verification:
the eigenvalues of 320 models, disk and delay margins, and μ on an LFT of 12 real parameters plus a complex drive
weight for the delay, lag and unmodelled dynamics.

| balance law | disk margin α (nominal / worst) | delay margin | μ RS mixed | balance_push | push peak V | tail V rms |
| --- | --- | --- | --- | --- | --- | --- |
| nominal LQR | 0.61 / 0.57 | 6 samples | 0.27 | 64/64 | 21.3 V | 1.45 V |
| **multi-model LQR** | **0.78** / 0.57 | **32** | 0.50 | 64/64 | **16.1 V** | **0.78 V** |
| structured H∞ | 0.46 / 0.32 | 5 | 0.59 | 49/64 | 24 V | 1.82 V |
| μ (D-K) | 0.55 / 0.47 | 7 | 0.26 | 64/64 | 20.8 V | 1.26 V |
| Glover-McFarlane | 0.36 / 0.10 | 14 | 0.77 | 58/64 | 19.2 V | 0.91 V |

- **Robust stability holds for every law**: the mixed μ bound stays at or below 0.77. The complex bound
  (above 1 for four laws) overstates it, up to 3 times.
- **The multi-model LQR is the best on the test**: half the voltage noise, 24 % less voltage for the push, the
  largest disk margin and a 32-sample delay margin. It is the balance law of the robust firmware.
- Structured H∞ has the best linear worst case, but its low gains saturate after the lean plus push.

**C2, swing-up for the box** (`design/robust_c2.py`). One open-loop plan cannot swing the double pendulum up
over the parameter box (the min-max plan ends far from upright), so the robustness has to come from the
feedback. The kept plan is the nominal one with a **multi-model TVLQR** against 17 models (`mm_tvlqr`); it and a
60 % / ±0.7 m margin plan pass `swingup` 64/64, as the nominal plan does. The box does not stress the TVLQR.

**C3, state-driven recovery** (`design/robust_ctrl.py`, `mode=rearm`). A timed swing-up cannot recover from a
knock-down (the nominal firmware: 0/64). The state machine of the robust firmware can:

1. **Drop**: a link more than 20° from upright switches balance (phase 2) to settle (phase 3).
2. **Settle**: a rail guard brakes when the stopping point passes 0.8 m; the links' energy is removed through
   the cart ($a = -k_E P_x$ minus centring, applied by the collocated partial feedback linearisation); below
   3.8 J a hanging LQR settles links and cart.
3. **Re-arm**: 50 ms at the hanging rest arm the TVLQR swing-up again (phase 1), shifted to the cart position
   and the links' turn count; the catch is inside the balance law's region $z^T P z <$ tol.

| C3 with the multi-model LQR (`c3-rearm-mm_lqr`) | success | catch (median / max) | peak V | peak x |
| --- | --- | --- | --- | --- |
| swingup | 64/64 | 2.61 / 3.22 s | 18.1 V | 0.40 m |
| balance_push | 64/64 | 2.93 / 2.97 s | 16.1 V | 0.23 m |
| knockdown_recover | **64/64** | 12.94 / 13.64 s | 24 V | **0.80 m** |

Pure energy pumping to the upright never caught within 20 s (the energy goes into a whirl of link 2), so the
swing-up itself stays the planned TVLQR, re-armed by the state machine.

**In bgsim** the firmware is one 1 kHz `@discrete` block, `library/DoubleCartLabRobustCtrl.jl` (the mm_lqr
gains, the steady-state EKF gain, the 2 ms delay, the C3 state machine with `rearm = 1`), with the `mm_tvlqr`
tables in `DoubleCartLabRobustTraj.jl`. A Python replica on the twin switches phase at the same ticks (within
1 ms).
