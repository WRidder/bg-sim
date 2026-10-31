/* bg-sim fixed-step solver core (hand-written, model independent; runtime 0.3.0).
 *
 * One call of bg_step advances exactly BG_DT:
 *   1. integrate the continuous states over [t, t + BG_DT] with the held discrete values
 *      constant (explicit Euler, RK4, or a linearly implicit Rosenbrock method), and the
 *      switching conditions frozen at their values at t (bg_modes);
 *   2. apply the `@events` whose condition crossed zero upward in the step (bg_events,
 *      generated; the conditions are evaluated at both ends of the step, the crossing is
 *      not located, so an event is up to one BG_DT late);
 *   3. run the discrete partitions due at t + BG_DT, in topological order, with the same
 *      operation order as the Julia scheduler (`run_tick!` in src/sim/scheduler.jl).
 * Events before ticks is the simulator's order: a tick at t runs after every event up to t.
 *
 * Real-time rules: no allocation, no recursion, no I/O, every loop bounded by a compile-time
 * size. The cost of a step is fixed: Euler is 1 derivative call, RK4 4. A Rosenbrock step is
 * 1 Jacobian, 1 LU (dense, or the static sparse LU of model.c with BG_SPARSE_LU),
 * BG_NSTAGE derivative calls and BG_NSTAGE solves, plus 1 derivative call for df/dt when the
 * right-hand side depends on t (BG_HAS_T). A DAE (BG_NALG > 0) re-solves its algebraic
 * unknowns after a tick or a fired event by Newton: at most 8 Jacobians and 8 derivative
 * calls, fewer once it has converged.
 */
#include <math.h>
#include <string.h>
#include "model.h"

static int bg_finite(const double *v, int n) {
    for (int i = 0; i < n; ++i) {
        if (!isfinite(v[i])) return 0;
    }
    return 1;
}

#if BG_METHOD == BG_METHOD_EULER

static int bg_integrate(bg_model *m, double t, double h) {
    bg_derivatives(m, t, m->x, m->k1);
    for (int i = 0; i < BG_NX; ++i) m->x[i] += h * m->k1[i];
    return 0;
}

#elif BG_METHOD == BG_METHOD_RK4

static int bg_integrate(bg_model *m, double t, double h) {
    double *x = m->x, *xs = m->xs;
    bg_derivatives(m, t, x, m->k1);
    for (int i = 0; i < BG_NX; ++i) xs[i] = x[i] + 0.5 * h * m->k1[i];
    bg_derivatives(m, t + 0.5 * h, xs, m->k2);
    for (int i = 0; i < BG_NX; ++i) xs[i] = x[i] + 0.5 * h * m->k2[i];
    bg_derivatives(m, t + 0.5 * h, xs, m->k3);
    for (int i = 0; i < BG_NX; ++i) xs[i] = x[i] + h * m->k3[i];
    bg_derivatives(m, t + h, xs, m->k4);
    for (int i = 0; i < BG_NX; ++i)
        x[i] += h / 6.0 * (m->k1[i] + 2.0 * m->k2[i] + 2.0 * m->k3[i] + m->k4[i]);
    return 0;
}

#else /* Rosenbrock: BG_METHOD_ROS2, BG_METHOD_ROS34PW2, BG_METHOD_RODAS4P */

/* The linear algebra goes through bg_w_factor / bg_w_solve (model.h). These are the dense
   versions; with BG_SPARSE_LU, model.c holds a generated static sparse LU instead. Both
   form W from m->jac, which bg_jacobian fills in the layout of the LU (BG_NJ entries). */
#ifndef BG_SPARSE_LU

/* In-place LU with partial pivoting of the row-major BG_NX x BG_NX matrix a. */
static int bg_lu(double *a, int *piv) {
    for (int k = 0; k < BG_NX; ++k) {
        int p = k;
        double best = fabs(a[k * BG_NX + k]);
        for (int i = k + 1; i < BG_NX; ++i) {
            double v = fabs(a[i * BG_NX + k]);
            if (v > best) { best = v; p = i; }
        }
        piv[k] = p;
        if (best == 0.0) return -1;
        /* Exchange only columns k.. : the multipliers of earlier columns stay where they were
           computed, which is the order bg_lu_solve applies the exchanges in (LINPACK). */
        if (p != k) {
            for (int j = k; j < BG_NX; ++j) {
                double tmp = a[k * BG_NX + j];
                a[k * BG_NX + j] = a[p * BG_NX + j];
                a[p * BG_NX + j] = tmp;
            }
        }
        double inv = 1.0 / a[k * BG_NX + k];
        for (int i = k + 1; i < BG_NX; ++i) {
            double f = a[i * BG_NX + k] * inv;
            a[i * BG_NX + k] = f;
            for (int j = k + 1; j < BG_NX; ++j) a[i * BG_NX + j] -= f * a[k * BG_NX + j];
        }
    }
    return 0;
}

static void bg_lu_solve(const double *a, const int *piv, double *b) {
    for (int k = 0; k < BG_NX; ++k) {
        int p = piv[k];
        if (p != k) { double tmp = b[k]; b[k] = b[p]; b[p] = tmp; }
        for (int i = k + 1; i < BG_NX; ++i) b[i] -= a[i * BG_NX + k] * b[k];
    }
    for (int k = BG_NX - 1; k >= 0; --k) {
        double s = b[k];
        for (int j = k + 1; j < BG_NX; ++j) s -= a[k * BG_NX + j] * b[j];
        b[k] = s / a[k * BG_NX + k];
    }
}

/* W = M - hg J from the dense Jacobian m->jac and the mass diagonal bg_mass, factored in
   place into m->w. Non-zero on an exactly singular pivot. */
int bg_w_factor(bg_model *m, double hg) {
    for (int i = 0; i < BG_NX * BG_NX; ++i) m->w[i] = -hg * m->jac[i];
    for (int i = 0; i < BG_NX; ++i) m->w[i * BG_NX + i] += bg_mass[i];
    return bg_lu(m->w, m->piv);
}

void bg_w_solve(bg_model *m, double *b) { bg_lu_solve(m->w, m->piv, b); }

#endif /* BG_SPARSE_LU */

/* Tableaus in the transformed form of Hairer and Wanner (IV.7, VI.4), as OrdinaryDiffEq
 * writes them. For M x' = f(t, x), with W = M - gamma h J and stage values u_i:
 *
 *   u_i = x + sum_{j<i} a_ij k_j
 *   W k_i = gamma h (f(t + c_i h, u_i) + d_i h df/dt + M sum_{j<i} (c_ij / h) k_j)
 *   x+  = x + sum_i b_i k_i
 *
 * The mass matrix only multiplies the stage coupling term, so an algebraic row (M_ii = 0)
 * is solved, linearised, at every stage: index-1 DAEs need no special treatment.
 *
 * ROS2      Verwer, Spee, Blom, Hundsdorfer (1999): 2 stages, order 2, L-stable.
 * ROS34PW2  Rang, Angermann (2005): 4 stages, order 3, L-stable, stiffly accurate, a
 *           W-method (keeps its order with an approximate Jacobian), order 3 for index-1
 *           DAEs.
 * RODAS4P   Steinebach (1995): 6 stages, order 4, L-stable, stiffly accurate, order 4 for
 *           index-1 DAEs and no order reduction on the Prothero-Robinson problem.
 * The Julia copy of the same numbers (src/export/analysis.jl) gives the stability functions
 * of the step analysis; the tests check both against OrdinaryDiffEq. */
#if BG_METHOD == BG_METHOD_ROS2
#define BG_S 2
static const double bg_gamma = 1.7071067811865475;
static const double bg_a[BG_S][BG_S] = {{0.0, 0.0}, {0.585786437626905, 0.0}};
static const double bg_cc[BG_S][BG_S] = {{0.0, 0.0}, {-1.17157287525381, 0.0}};
static const double bg_c[BG_S] = {0.0, 1.0};
static const double bg_d[BG_S] = {1.7071067811865475, -1.7071067811865475};
static const double bg_b[BG_S] = {0.8786796564403574, 0.2928932188134525};
#elif BG_METHOD == BG_METHOD_ROS34PW2
#define BG_S 4
static const double bg_gamma = 0.435866521508459;
static const double bg_a[BG_S][BG_S] = {
    {0.0, 0.0, 0.0, 0.0},
    {2.0, 0.0, 0.0, 0.0},
    {1.4192173174557647, -0.2592322116729697, 0.0, 0.0},
    {4.18476048231916, -0.28519201735549593, 2.294280360279042, 0.0}};
static const double bg_cc[BG_S][BG_S] = {
    {0.0, 0.0, 0.0, 0.0},
    {-4.588560720558084, 0.0, 0.0, 0.0},
    {-4.18476048231916, 0.28519201735549593, 0.0, 0.0},
    {-6.368179200128359, -6.795620944466837, 2.8700986043310563, 0.0}};
static const double bg_c[BG_S] = {0.0, 0.871733043016918, 0.7315799577888524, 1.0};
static const double bg_d[BG_S] = {0.435866521508459, -0.435866521508459,
                                  -0.4133333762338865, -5.551115123125783e-17};
static const double bg_b[BG_S] = {4.1847604823191595, -0.28519201735549565,
                                  2.2942803602790414, 1.0};
#elif BG_METHOD == BG_METHOD_RODAS4P
#define BG_S 6
static const double bg_gamma = 0.25;
static const double bg_a[BG_S][BG_S] = {
    {0.0, 0.0, 0.0, 0.0, 0.0, 0.0},
    {3.0, 0.0, 0.0, 0.0, 0.0, 0.0},
    {1.831036793486759, 0.4955183967433795, 0.0, 0.0, 0.0, 0.0},
    {2.304376582692669, -0.05249275245743001, -1.176798761832782, 0.0, 0.0, 0.0},
    {-7.170454962423024, -4.741636671481785, -16.31002631330971, -1.062004044111401, 0.0, 0.0},
    {-7.170454962423024, -4.741636671481785, -16.31002631330971, -1.062004044111401, 1.0, 0.0}};
static const double bg_cc[BG_S][BG_S] = {
    {0.0, 0.0, 0.0, 0.0, 0.0, 0.0},
    {-12.0, 0.0, 0.0, 0.0, 0.0, 0.0},
    {-8.791795173947035, -2.207865586973518, 0.0, 0.0, 0.0, 0.0},
    {10.81793056857153, 6.780270611428266, 19.5348594464241, 0.0, 0.0, 0.0},
    {34.19095006749676, 15.49671153725963, 54.7476087596413, 14.16005392148534, 0.0, 0.0},
    {34.62605830930532, 15.30084976114473, 56.99955578662667, 18.40807009793095,
     -5.714285714285717, 0.0}};
static const double bg_c[BG_S] = {0.0, 0.75, 0.21, 0.63, 1.0, 1.0};
static const double bg_d[BG_S] = {0.25, -0.5, -0.023504, -0.0362, 0.0, 0.0};
static const double bg_b[BG_S] = {-7.170454962423024, -4.741636671481785, -16.31002631330971,
                                  -1.062004044111401, 1.0, 1.0};
#else
#error "unknown BG_METHOD"
#endif

#if BG_S != BG_NSTAGE
#error "BG_NSTAGE in model.h does not match the method"
#endif

static int bg_integrate(bg_model *m, double t, double h) {
    double *x = m->x, *u = m->xs, *f = m->fx;
    const double hg = h * bg_gamma;
    memset(m->jac, 0, sizeof m->jac);
    bg_jacobian(m, t, x, m->jac);
    if (bg_w_factor(m, hg) != 0) return -1;
    bg_derivatives(m, t, x, f);
#if BG_HAS_T
    /* df/dt by a forward difference, with the switching conditions still frozen. */
    {
        const double tau = 1.4901161193847656e-8 * (fabs(t) > 1.0 ? fabs(t) : 1.0);
        bg_derivatives(m, t + tau, x, m->ft);
        for (int i = 0; i < BG_NX; ++i) m->ft[i] = (m->ft[i] - f[i]) / tau;
    }
#endif
    for (int s = 0; s < BG_S; ++s) {
        double *k = m->ks[s];
        if (s > 0) {
            for (int i = 0; i < BG_NX; ++i) {
                double v = x[i];
                for (int j = 0; j < s; ++j) v += bg_a[s][j] * m->ks[j][i];
                u[i] = v;
            }
            bg_derivatives(m, t + bg_c[s] * h, u, f);
        }
        for (int i = 0; i < BG_NX; ++i) {
            double acc = 0.0;
            for (int j = 0; j < s; ++j) acc += bg_cc[s][j] * m->ks[j][i];
            double r = f[i] + bg_mass[i] * acc / h;
#if BG_HAS_T
            r += bg_d[s] * h * m->ft[i];
#endif
            k[i] = hg * r;
        }
        bg_w_solve(m, k);
    }
    for (int i = 0; i < BG_NX; ++i) {
        double v = x[i];
        for (int s = 0; s < BG_S; ++s) v += bg_b[s] * m->ks[s][i];
        x[i] = v;
    }
    (void)bg_d;
    return 0;
}

#if BG_NALG > 0
/* After a discrete tick the held values have changed, so the algebraic unknowns no longer
   solve their equations at the current differential state. They are re-solved as the
   simulation does (FIX-M2-3): Newton iterations on 0 = g(x_d, z) with x_d fixed, by Gaussian
   elimination with partial pivoting on the BG_NALG x BG_NALG block dg/dz (read from m->jac
   through bg_alg_jpos, so it works with either layout of J). A held input or an event can
   jump, so the Jacobian is evaluated again in every iteration (a frozen one diverges on the
   FIX-M2-3 fixture). At most BG_NEWTON iterations, so the worst case is bounded: BG_NEWTON
   Jacobians and derivative calls per tick. A singular block leaves z as it is; the next step
   then solves the constraint linearised.
   With BG_SPARSE_PROJECT (the static sparse LU, and dg/dz passed its pivot check at export)
   the Newton step is factored on the static tables instead (bg_alg_factor, bg_w_solve), in
   the workspace of the step's LU; a bad pivot falls back to the dense elimination. */
#define BG_NEWTON 8
/* One Newton step on the algebraic block by Gaussian elimination with partial pivoting:
   m->ga receives dz with dg/dz dz = -g. Non-zero on a singular block. */
static int bg_alg_dense(bg_model *m) {
    double *a = m->wa, *g = m->ga;
    for (int i = 0; i < BG_NALG; ++i) {
        g[i] = -m->fx[bg_alg[i]];
        for (int j = 0; j < BG_NALG; ++j) {
            const int q = bg_alg_jpos[i * BG_NALG + j];
            a[i * BG_NALG + j] = q < 0 ? 0.0 : m->jac[q];
        }
    }
    for (int k = 0; k < BG_NALG; ++k) {
        int p = k;
        double best = fabs(a[k * BG_NALG + k]);
        for (int i = k + 1; i < BG_NALG; ++i) {
            double v = fabs(a[i * BG_NALG + k]);
            if (v > best) { best = v; p = i; }
        }
        if (best == 0.0) return -1;
        if (p != k) {
            for (int j = k; j < BG_NALG; ++j) {
                double tmp = a[k * BG_NALG + j];
                a[k * BG_NALG + j] = a[p * BG_NALG + j];
                a[p * BG_NALG + j] = tmp;
            }
            double tmp = g[k]; g[k] = g[p]; g[p] = tmp;
        }
        for (int i = k + 1; i < BG_NALG; ++i) {
            double f = a[i * BG_NALG + k] / a[k * BG_NALG + k];
            for (int j = k + 1; j < BG_NALG; ++j) a[i * BG_NALG + j] -= f * a[k * BG_NALG + j];
            g[i] -= f * g[k];
        }
    }
    for (int k = BG_NALG - 1; k >= 0; --k) {
        double s = g[k];
        for (int j = k + 1; j < BG_NALG; ++j) s -= a[k * BG_NALG + j] * g[j];
        g[k] = s / a[k * BG_NALG + k];
    }
    return 0;
}

static void bg_project(bg_model *m, double t) {
    double *g = m->ga;
    for (int it = 0; it < BG_NEWTON; ++it) {
        memset(m->jac, 0, sizeof m->jac);
        bg_jacobian(m, t, m->x, m->jac);
        bg_derivatives(m, t, m->x, m->fx);
#ifdef BG_SPARSE_PROJECT
        if (bg_alg_factor(m) == 0) {
            double *r = m->xs;   /* the stage workspace is free between steps */
            for (int i = 0; i < BG_NX; ++i) r[i] = 0.0;
            for (int i = 0; i < BG_NALG; ++i) r[bg_alg[i]] = -m->fx[bg_alg[i]];
            bg_w_solve(m, r);
            for (int i = 0; i < BG_NALG; ++i) g[i] = r[bg_alg[i]];
        } else
#endif
        if (bg_alg_dense(m) != 0) return;
        int done = 1;
        for (int i = 0; i < BG_NALG; ++i) {
            double *z = &m->x[bg_alg[i]];
            *z += g[i];
            if (fabs(g[i]) > 1e-13 * (1.0 + fabs(*z))) done = 0;
        }
        if (done) return;
    }
}
#endif

#endif

void bg_reset(bg_model *m, double t_start) {
    memset(m, 0, sizeof *m);
    m->t = t_start;
    m->t_start = t_start;
    m->t_start_ns = (int64_t)llround(t_start * 1e9);
    for (int i = 0; i < BG_NX; ++i) m->x[i] = bg_x0[i];
    for (int i = 0; i < BG_NP; ++i) m->p[i] = bg_p0[i];
    for (int i = 0; i < BG_NU; ++i) m->u[i] = bg_u0[i];
    for (int i = 0; i < BG_ND; ++i) m->d[i] = m->dprev[i] = bg_d0[i];
    m->dprev_t = t_start;
}

/* The Julia scheduler's tick (run_tick!): snapshot for previous(x), then each due partition
   samples the continuous values and runs; finally the inputs are re-sampled. */
static void bg_tick(bg_model *m, double t, int64_t ns) {
    int any = 0;
    for (int k = 0; k < BG_NPART; ++k) {
        const bg_partition *p = &bg_partitions[k];
        if (p->period_ns <= 0 || ns < p->offset_ns || (ns - p->offset_ns) % p->period_ns != 0)
            continue;
        if (!any) {
            for (int i = 0; i < BG_NI; ++i) m->dinprev[i] = m->din[i];
            for (int i = 0; i < BG_ND; ++i) m->dprev[i] = m->d[i];
            m->dprev_t = t;
            any = 1;
        }
        bg_sample(m, t, m->x, m->din);
        p->run(m, t);
    }
    if (!any) return;
#if BG_NALG > 0
    bg_project(m, t);
#endif
    bg_sample(m, t, m->x, m->din);
}

int bg_step(bg_model *m) {
    double t0 = m->t;
    int64_t ns1 = m->t_start_ns + (m->n + 1) * BG_DT_NS;
    double t1 = (double)ns1 / 1e9;
    /* Every switching condition is evaluated once, at the start of the step, and held for all
       stages, so each step integrates a smooth right-hand side. A switch exactly on a step
       boundary is then exact; one inside a step takes effect at the next boundary (W203). */
    if (BG_NC > 0) bg_modes(m, t0, m->x, m->c);
    if (BG_NE > 0) bg_event_conditions(m, t0, m->x, m->ez0);
    if (bg_integrate(m, t0, t1 - t0) != 0) return -1;
    if (BG_NE > 0 && bg_events(m, t1) > 0) {
#if BG_NALG > 0 && BG_NSTAGE > 0
        /* A reinit moved the states, so the algebraic unknowns are re-solved as after a tick. */
        bg_project(m, t1);
#endif
    }
    if (!bg_finite(m->x, BG_NX)) return -2;
    m->n += 1;
    m->t = t1;
    if (BG_NPART > 0) bg_tick(m, t1, ns1);
    m->y_valid = 0;
    return 0;
}

void bg_update_outputs(bg_model *m) {
    if (!m->y_valid) {
        bg_outputs(m, m->t, m->x, m->y);
        m->y_valid = 1;
    }
}
