/* bg-sim C runtime helpers: the language semantics the generated code relies on.
   Each mirrors the Julia lowering exactly (src/lower/fnmap.jl `lower_nonsmooth` and the
   `DiscreteRuntime` module in src/sim/scheduler.jl). Header-only, no libc beyond math.h. */
#ifndef BG_RUNTIME_H
#define BG_RUNTIME_H

#include <math.h>

/* `sign(-0.0)` is 0.0, as in the Julia lowering. */
static inline double bg_sign(double x) { return x > 0.0 ? 1.0 : (x < 0.0 ? -1.0 : 0.0); }

/* Round half away from zero. */
static inline double bg_round(double x) { return x >= 0.0 ? floor(x + 0.5) : ceil(x - 0.5); }

static inline double bg_clamp(double x, double lo, double hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static inline double bg_deadzone(double x, double lo, double hi) {
    return x > hi ? x - hi : (x < lo ? x - lo : 0.0);
}

/* Julia `min`/`max` on non-NaN values. */
static inline double bg_min(double a, double b) { return b < a ? b : a; }
static inline double bg_max(double a, double b) { return b > a ? b : a; }

/* Julia `mod`: the result has the sign of the divisor. */
static inline double bg_mod(double x, double y) {
    double r = fmod(x, y);
    return (r != 0.0 && ((r < 0.0) != (y < 0.0))) ? r + y : r;
}

#endif
