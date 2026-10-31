/* Golden-test driver for the C runtime intrinsics (test/test_export_intrinsics.jl).

   Reads one call per line from stdin, `<function> <arguments...>`, and prints the results
   on one line. Every number, in and out, is the 64-bit pattern of a double in 16 hex
   digits, so the transport is exact (the msvcrt scanf/printf do not round correctly). Tables
   are passed inline: `bg_interp1 n u xs... ys...` and `bg_interp2 n u v breaks... table...`
   (both row-major). Test code only: stdio is fine here, never in the hot path. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "bg_intrinsics.h"
#include "bg_mech.h"

#define MAXV 4096

static double buf_a[MAXV], buf_b[MAXV];

static int read_one(double *v) {
    char tok[32];
    uint64_t bits = 0;
    int k;
    if (scanf("%31s", tok) != 1 || strlen(tok) != 16) return 0;
    for (k = 0; k < 16; ++k) {
        char c = tok[k];
        int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
        if (d < 0) return 0;
        bits = (bits << 4) | (uint64_t)d;
    }
    memcpy(v, &bits, sizeof bits);
    return 1;
}

static int read_n(double *v, int n) {
    int k;
    if (n < 0 || n > MAXV) return 0;
    for (k = 0; k < n; ++k) {
        if (!read_one(&v[k])) return 0;
    }
    return 1;
}

static void put(double x) {
    uint64_t bits;
    int k;
    memcpy(&bits, &x, sizeof bits);
    putchar(' ');
    for (k = 15; k >= 0; --k) putchar("0123456789abcdef"[(bits >> (4 * k)) & 0xf]);
}

static void put_n(const double *v, int n) {
    int k;
    for (k = 0; k < n; ++k) put(v[k]);
    printf("\n");
}

int main(void) {
    char name[64];
    double a[16], out[8];
    while (scanf("%63s", name) == 1) {
        if (strcmp(name, "bg_exp2") == 0 && read_n(a, 3)) {
            bg_exp2(a[0], a[1], a[2], out);
            put_n(out, 3);
        } else if (strcmp(name, "bg_log2") == 0 && read_n(a, 3)) {
            bg_log2(a[0], a[1], a[2], out);
            put_n(out, 3);
        } else if (strcmp(name, "bg_exp3") == 0 && read_n(a, 6)) {
            bg_exp3(a[0], a[1], a[2], a[3], a[4], a[5], out);
            put_n(out, 7);
        } else if (strcmp(name, "bg_log3") == 0 && read_n(a, 7)) {
            bg_log3(a[0], a[1], a[2], a[3], a[4], a[5], a[6], out);
            put_n(out, 6);
        } else if (strcmp(name, "bg_quat_exp") == 0 && read_n(a, 3)) {
            bg_quat_exp(a[0], a[1], a[2], out);
            put_n(out, 4);
        } else if (strcmp(name, "bg_quat_log") == 0 && read_n(a, 4)) {
            bg_quat_log(a[0], a[1], a[2], a[3], out);
            put_n(out, 3);
        } else if (strcmp(name, "bg_quat_from_rotation") == 0 && read_n(a, 9)) {
            bg_quat_from_rotation(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], out);
            put_n(out, 4);
        } else if (strcmp(name, "bg_inertia2") == 0 && read_n(a, 6)) {
            out[0] = bg_inertia2(a[0], a[1], a[2], a[3], (int)a[4], (int)a[5]);
            put_n(out, 1);
        } else if (strcmp(name, "bg_inertia3") == 0 && read_n(a, 9)) {
            out[0] = bg_inertia3(a[0], a[1], a[2], a[3], a[4], a[5], a[6], (int)a[7], (int)a[8]);
            put_n(out, 1);
        } else if (strcmp(name, "bg_interp1") == 0 && read_n(a, 2)) {
            int n = (int)a[0];
            if (!read_n(buf_a, n) || !read_n(buf_b, n)) return 2;
            out[0] = bg_interp1(a[1], buf_a, buf_b, n);
            put_n(out, 1);
        } else if (strcmp(name, "bg_interp2") == 0 && read_n(a, 3)) {
            int n = (int)a[0];
            if (!read_n(buf_a, 2 * n) || !read_n(buf_b, n * n)) return 2;
            out[0] = bg_interp2(a[1], a[2], buf_a, buf_b, n);
            put_n(out, 1);
        } else if (strcmp(name, "bg_noise_uniform") == 0 && read_n(a, 2)) {
            out[0] = bg_noise_uniform(a[0], a[1]);
            put_n(out, 1);
        } else if (strcmp(name, "bg_noise_normal") == 0 && read_n(a, 2)) {
            out[0] = bg_noise_normal(a[0], a[1]);
            put_n(out, 1);
        } else {
            fprintf(stderr, "bad input at `%s`\n", name);
            return 2;
        }
    }
    return 0;
}
