/* Batched environment over the plain C API of a bg-sim export (plan/RL_PLAN.md R0.2).
 *
 * N instances of the exported model (bg_model, model.h) live in one array. One call steps all
 * of them by `nsub` internal steps with the inputs held, reads the outputs, and reports a
 * status per instance; the loop over instances runs on OpenMP threads (BGENV_THREADS, or
 * omp_set_num_threads through bgenv_set_threads). Python passes numpy buffers through ctypes.
 *
 * Reset of instance k: bg_reset (the export's start), the fixed parameters set before
 * initialisation (refused outside their declared range, as fmi2SetReal does), bg_init (the
 * calculated parameters and starts, J-EX8), then optional state overrides (a pose at rest:
 * the joint angle integrators, the momenta stay zero). Writing m->x directly is outside the
 * FMI interface; the state indices come from the comments of model.c (rl/rlpend/cbuild.py).
 */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#ifdef _OPENMP
#include <omp.h>
#endif
#include "model.h"

#if defined(_WIN32)
#define BGENV_API __declspec(dllexport)
#else
#define BGENV_API __attribute__((visibility("default")))
#endif

typedef struct {
    int n;
    bg_model *m;
    double t_plant_ns;   /* time inside bg_step, summed over all calls (thread 0's share) */
} bgenv;

BGENV_API int bgenv_nx(void) { return BG_NX; }
BGENV_API int bgenv_np(void) { return BG_NP; }
BGENV_API int bgenv_nu(void) { return BG_NU; }
BGENV_API int bgenv_ny(void) { return BG_NY; }
BGENV_API double bgenv_dt(void) { return BG_DT; }
BGENV_API int bgenv_method(void) { return BG_METHOD; }
BGENV_API const char *bgenv_p_name(int i) { return (i >= 0 && i < BG_NP) ? bg_p_name[i] : NULL; }
BGENV_API const char *bgenv_u_name(int i) { return (i >= 0 && i < BG_NU) ? bg_u_name[i] : NULL; }
BGENV_API int bgenv_p_kind(int i) { return (i >= 0 && i < BG_NP) ? bg_p_tunable[i] : -1; }
BGENV_API double bgenv_p_min(int i) { return bg_p_min[i]; }
BGENV_API double bgenv_p_max(int i) { return bg_p_max[i]; }
BGENV_API double bgenv_p0(int i) { return bg_p0[i]; }

BGENV_API void bgenv_set_threads(int k) {
#ifdef _OPENMP
    if (k > 0) omp_set_num_threads(k);
#else
    (void)k;
#endif
}

BGENV_API int bgenv_threads(void) {
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

BGENV_API bgenv *bgenv_create(int n) {
    bgenv *e = (bgenv *)calloc(1, sizeof *e);
    if (!e) return NULL;
    e->n = n;
    e->m = (bg_model *)calloc((size_t)n, sizeof(bg_model));
    if (!e->m) { free(e); return NULL; }
    for (int k = 0; k < n; ++k) {
        bg_reset(&e->m[k], 0.0);
        bg_init(&e->m[k]);
    }
    return e;
}

BGENV_API void bgenv_free(bgenv *e) {
    if (!e) return;
    free(e->m);
    free(e);
}

/* Reset the instances k with mask[k] != 0. `pv` is n x npset (row k: the values of the
   parameters pidx[0..npset)), `xv` n x nxset (the states xidx[0..nxset) after init).
   Returns 0, or 1 + k of the first instance whose parameter was out of range or whose
   initialisation failed (that instance is left at the export's start). */
BGENV_API int bgenv_reset(bgenv *e, const unsigned char *mask,
                          const int *pidx, int npset, const double *pv,
                          const int *xidx, int nxset, const double *xv) {
    int bad = 0;
    for (int k = 0; k < e->n; ++k) {
        if (mask && !mask[k]) continue;
        bg_model *m = &e->m[k];
        bg_reset(m, 0.0);
        int ok = 1;
        for (int j = 0; j < npset; ++j) {
            int i = pidx[j];
            double v = pv[(size_t)k * npset + j];
            if (i < 0 || i >= BG_NP || bg_p_tunable[i] == 2 || !(v >= bg_p_min[i] && v <= bg_p_max[i])) {
                ok = 0;
                break;
            }
            m->p[i] = v;
        }
        if (ok && bg_init(m) != 0) ok = 0;
        if (!ok) {
            bg_reset(m, 0.0);
            bg_init(m);
            if (!bad) bad = 1 + k;
            continue;
        }
        for (int j = 0; j < nxset; ++j) m->x[xidx[j]] = xv[(size_t)k * nxset + j];
        m->y_valid = 0;
    }
    return bad;
}

static double now_ns(void) {
#ifdef _OPENMP
    return omp_get_wtime() * 1e9;
#else
    return (double)clock() * (1e9 / CLOCKS_PER_SEC);
#endif
}

/* Step every instance by nsub internal steps (nsub * BG_DT seconds) with the inputs u
   (n x BG_NU) held; write the outputs (n x BG_NY) and the status (0 ok, else the first
   nonzero bg_step result). An instance with a nonzero status is not stepped again until it
   is reset (its outputs stay those of its last good step). Returns the number of failures. */
BGENV_API int bgenv_step(bgenv *e, const double *u, int nsub, double *y, int *status) {
    int fails = 0;
    double t0 = now_ns();
#pragma omp parallel for schedule(static) reduction(+ : fails)
    for (int k = 0; k < e->n; ++k) {
        bg_model *m = &e->m[k];
        if (status[k] == 0) {
            for (int i = 0; i < BG_NU; ++i) m->u[i] = u[(size_t)k * BG_NU + i];
            for (int s = 0; s < nsub; ++s) {
                int r = bg_step(m);
                if (r != 0) { status[k] = r; break; }
            }
        }
        if (status[k] != 0) fails += 1;
        bg_update_outputs(m);
        memcpy(&y[(size_t)k * BG_NY], m->y, sizeof(double) * BG_NY);
    }
    e->t_plant_ns += now_ns() - t0;
    return fails;
}

BGENV_API double bgenv_plant_seconds(bgenv *e) { return e->t_plant_ns * 1e-9; }

BGENV_API void bgenv_outputs(bgenv *e, double *y) {
    for (int k = 0; k < e->n; ++k) {
        bg_update_outputs(&e->m[k]);
        memcpy(&y[(size_t)k * BG_NY], e->m[k].y, sizeof(double) * BG_NY);
    }
}

BGENV_API void bgenv_get_x(bgenv *e, double *x) {
    for (int k = 0; k < e->n; ++k) memcpy(&x[(size_t)k * BG_NX], e->m[k].x, sizeof(double) * BG_NX);
}

BGENV_API void bgenv_set_x(bgenv *e, int k, const double *x) {
    memcpy(e->m[k].x, x, sizeof(double) * BG_NX);
    e->m[k].y_valid = 0;
}

BGENV_API double bgenv_time(bgenv *e, int k) { return e->m[k].t; }
