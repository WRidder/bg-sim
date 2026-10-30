/* bg-sim C runtime: the table intrinsics (see bg_intrinsics.h). The arithmetic follows the
   Julia bodies term by term, so the results are bit-identical to Julia for the same
   interval; the golden tests in test/test_export_intrinsics.jl check it. */
#include <math.h>
#include "bg_intrinsics.h"

/* The interval [x[k], x[k+1]] the Julia scan stops at: the first k in [0, n-2] with
   u <= x[k+1], or n-2. Needs n >= 2. */
static int bg_segment(const double *x, int n, double u) {
    int lo = 0, hi = n - 2;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (u > x[mid + 1]) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    return lo;
}

double bg_interp1(double u, const double *xs, const double *ys, int n) {
    int k;
    double x0, x1, w;
    if (u <= xs[0]) return ys[0];
    if (u >= xs[n - 1]) return ys[n - 1];
    if (n < 2) return ys[0];
    k = bg_segment(xs, n, u);
    x0 = xs[k];
    x1 = xs[k + 1];
    if (x1 == x0) return ys[k];
    w = (u - x0) / (x1 - x0);
    return (1.0 - w) * ys[k] + w * ys[k + 1];
}

double bg_interp2(double u, double v, const double *breaks, const double *table, int n) {
    const double *bx = breaks, *by = breaks + n;
    double ux = u, vx = v, x0, x1, y0, y1, fx, fy, low, high;
    int i, j;
    if (n < 2) return table[0];
    if (ux <= bx[0]) ux = bx[0];
    if (ux >= bx[n - 1]) ux = bx[n - 1];
    if (vx <= by[0]) vx = by[0];
    if (vx >= by[n - 1]) vx = by[n - 1];
    j = bg_segment(bx, n, ux);
    i = bg_segment(by, n, vx);
    x0 = bx[j]; x1 = bx[j + 1];
    y0 = by[i]; y1 = by[i + 1];
    fx = x1 == x0 ? 0.0 : (ux - x0) / (x1 - x0);
    fy = y1 == y0 ? 0.0 : (vx - y0) / (y1 - y0);
    low = (1.0 - fx) * table[i * n + j] + fx * table[i * n + j + 1];
    high = (1.0 - fx) * table[(i + 1) * n + j] + fx * table[(i + 1) * n + j + 1];
    return (1.0 - fy) * low + fy * high;
}
