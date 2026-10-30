/* bg-sim fixed-step solver core (hand-written, model independent; runtime 0.2.0).
 *
 * One call of bg_step advances exactly BG_DT:
 *   1. integrate the continuous states over [t, t + BG_DT] with the held discrete values
 *      constant (explicit Euler, RK4, or the 2-stage L-stable Rosenbrock method ROS2);
 *      and the switching conditions frozen at their values at t (bg_modes);
 *   2. apply the `@events` whose condition crossed zero upward in the step (bg_events,
 *      generated; the conditions are evaluated at both ends of the step, the crossing is
 *      not located, so an event is up to one BG_DT late);
 *   3. run the discrete partitions due at t + BG_DT, in topological order, with the same
 *      operation order as the Julia scheduler (`run_tick!` in src/sim/scheduler.jl).
 * Events before ticks is the simulator's order: a tick at t runs after every event up to t.
 *
 * Real-time rules: no allocation, no recursion, no I/O, every loop bounded by a compile-time
 * size. The cost of a step is fixed: Euler is 1 derivative call, RK4 4; ROS2 is 1 Jacobian, 1 LU of
 * BG_NX x BG_NX and 2 derivative calls.
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

#else /* BG_METHOD_ROS2 */

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
        if (p != k) {
            for (int j = 0; j < BG_NX; ++j) {
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

/* ROS2 (Verwer, Spee, Blom, Hundsdorfer 1999), gamma = 1 + 1/sqrt(2):
 *   W = I - gamma h J,  W k1 = f(t, x),  W k2 = f(t + h, x + h k1) - 2 k1,
 *   x+ = x + 3/2 h k1 + 1/2 h k2.
 * Second order, L-stable; the explicit time derivative of f is neglected (the spike's
 * sources are piecewise constant in t). */
static int bg_integrate(bg_model *m, double t, double h) {
    const double gamma = 1.7071067811865475;
    double *x = m->x, *xs = m->xs, *w = m->w;
    for (int i = 0; i < BG_NX * BG_NX; ++i) w[i] = 0.0;
    bg_jacobian(m, t, x, w);
    for (int i = 0; i < BG_NX * BG_NX; ++i) w[i] *= -gamma * h;
    for (int i = 0; i < BG_NX; ++i) w[i * BG_NX + i] += 1.0;
    if (bg_lu(w, m->piv) != 0) return -1;
    bg_derivatives(m, t, x, m->k1);
    bg_lu_solve(w, m->piv, m->k1);
    for (int i = 0; i < BG_NX; ++i) xs[i] = x[i] + h * m->k1[i];
    bg_derivatives(m, t + h, xs, m->k2);
    for (int i = 0; i < BG_NX; ++i) m->k2[i] -= 2.0 * m->k1[i];
    bg_lu_solve(w, m->piv, m->k2);
    for (int i = 0; i < BG_NX; ++i) x[i] += 1.5 * h * m->k1[i] + 0.5 * h * m->k2[i];
    return 0;
}

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
    if (any) bg_sample(m, t, m->x, m->din);
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
    if (BG_NE > 0) bg_events(m, t1);
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
