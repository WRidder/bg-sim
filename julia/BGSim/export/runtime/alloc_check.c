/* Allocation and timing harness: links the FMU sources statically, counts every call of the
 * memory callbacks, and fails if any happens after fmi2Instantiate. Then times fmi2DoStep.
 *
 *   alloc_check <steps_per_doStep> <doSteps>
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "fmi2Functions.h"
#include "model.h"

static long g_allocs = 0, g_frees = 0;

static void *count_alloc(size_t n, size_t size) { ++g_allocs; return calloc(n, size); }
static void count_free(void *p) { ++g_frees; free(p); }
static void log_msg(fmi2ComponentEnvironment env, fmi2String name, fmi2Status s,
                    fmi2String cat, fmi2String msg, ...) {
    (void)env; (void)cat;
    va_list ap;
    va_start(ap, msg);
    fprintf(stderr, "[%s status %d] ", name, (int)s);
    vfprintf(stderr, msg, ap);
    fputc('\n', stderr);
    va_end(ap);
}

#ifdef _WIN32
#include <windows.h>
static double now_s(void) {
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
}
#else
static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}
#endif

int main(int argc, char **argv) {
    long per = argc > 1 ? atol(argv[1]) : 10;
    long count = argc > 2 ? atol(argv[2]) : 100000;
    fmi2CallbackFunctions cb = {log_msg, count_alloc, count_free, NULL, NULL};
    fmi2Component c = fmi2Instantiate("check", fmi2CoSimulation, BG_GUID, "", &cb, fmi2False, fmi2False);
    if (c == NULL) { fprintf(stderr, "instantiate failed\n"); return 2; }
    long after_instantiate = g_allocs;
    fmi2SetupExperiment(c, fmi2False, 0.0, 0.0, fmi2False, 0.0);
    fmi2EnterInitializationMode(c);
    fmi2ExitInitializationMode(c);

    double h = per * BG_DT, t = 0.0, worst = 0.0, total = 0.0;
    fmi2ValueReference vr0 = 0;
    fmi2Real y = 0.0;
    for (long k = 0; k < count; ++k) {
        double a = now_s();
        if (fmi2DoStep(c, t, h, fmi2True) != fmi2OK) { fprintf(stderr, "doStep failed at %g\n", t); return 3; }
        fmi2GetReal(c, &vr0, 1, &y);
        double dtw = now_s() - a;
        total += dtw;
        if (dtw > worst) worst = dtw;
        t += h;
    }
    long during = g_allocs - after_instantiate;
    fmi2FreeInstance(c);
    printf("allocations: instantiate %ld, after instantiate %ld, frees %ld\n",
           after_instantiate, during, g_frees);
    printf("doStep (%ld internal steps of %g s): mean %.3f us, max %.3f us over %ld calls; y[0] = %.17g\n",
           per, BG_DT, 1e6 * total / count, 1e6 * worst, count, y);
    return during == 0 ? 0 : 1;
}
