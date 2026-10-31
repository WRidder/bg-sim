/* bg-sim FMI 2.0 Co-Simulation wrapper (hand-written, model independent; runtime 0.6.0).
 *
 * Memory: fmi2Instantiate allocates the one instance struct through the environment's
 * allocateMemory callback; nothing else is ever allocated. fmi2DoStep, fmi2GetReal and
 * fmi2SetReal touch only that struct. The logger is called only on an error.
 *
 * Parameters and inputs are refused outside their declared [min, max] (bg_p_min/bg_u_min
 * and friends): the export proved the step stable on that range and nowhere else. Inputs are
 * held constant over a doStep (zero-order hold).
 *
 * Parameters (bg_p_tunable): tunable ones can be set at any time, fixed ones (picked
 * tunables, exposed global parameters) only before fmi2ExitInitializationMode, calculated
 * ones never. fmi2ExitInitializationMode runs bg_init once (J-EX8): the calculated
 * parameters, starts and held values from the fixed ones, then, for a DAE, Newton on the
 * algebraic unknowns. Nothing of it runs in fmi2DoStep.
 */
#include <math.h>
#include <string.h>
#include "fmi2Functions.h"
#include "model.h"

typedef enum { ST_INSTANTIATED, ST_INIT, ST_STEP, ST_TERMINATED, ST_ERROR } bg_state;

typedef struct {
    bg_model m;
    fmi2CallbackFunctions cb;
    fmi2String name;
    bg_state state;
} bg_instance;

#define INST ((bg_instance *)c)

static fmi2Status bg_fail(bg_instance *in, fmi2Status status, const char *msg) {
    if (in != NULL && in->cb.logger != NULL)
        in->cb.logger(in->cb.componentEnvironment, in->name, status, "error", "%s", msg);
    if (in != NULL && status >= fmi2Error) in->state = ST_ERROR;
    return status;
}

/* A refusal that names the variable (the host's logger formats it; nothing is formatted
   here, so no stdio is linked). */
static fmi2Status bg_name_fail(bg_instance *in, const char *fmt, const char *name) {
    if (in->cb.logger != NULL)
        in->cb.logger(in->cb.componentEnvironment, in->name, fmi2Error, "error", fmt, name);
    in->state = ST_ERROR;
    return fmi2Error;
}

/* D-EX16: a value outside the declared range is refused, never clamped: the export proved
   the step stable on that range only, and a silently changed value would hide the mistake. */
static fmi2Status bg_range_fail(bg_instance *in, const char *what, const char *name, double v,
                                double lo, double hi) {
    if (in->cb.logger != NULL)
        in->cb.logger(in->cb.componentEnvironment, in->name, fmi2Error, "error",
                      "fmi2SetReal: %s %s = %g is outside its declared range [%g, %g]",
                      what, name, v, lo, hi);
    in->state = ST_ERROR;
    return fmi2Error;
}

const char *fmi2GetTypesPlatform(void) { return fmi2TypesPlatform; }
const char *fmi2GetVersion(void) { return fmi2Version; }

fmi2Status fmi2SetDebugLogging(fmi2Component c, fmi2Boolean on, size_t n, const fmi2String cats[]) {
    (void)c; (void)on; (void)n; (void)cats;
    return fmi2OK;
}

fmi2Component fmi2Instantiate(fmi2String name, fmi2Type type, fmi2String guid,
                              fmi2String location, const fmi2CallbackFunctions *functions,
                              fmi2Boolean visible, fmi2Boolean logging) {
    (void)location; (void)visible; (void)logging;
    if (functions == NULL || functions->allocateMemory == NULL || functions->freeMemory == NULL)
        return NULL;
    if (type != fmi2CoSimulation || guid == NULL || strcmp(guid, BG_GUID) != 0) {
        if (functions->logger != NULL)
            functions->logger(functions->componentEnvironment, name, fmi2Error, "error",
                              "only Co-Simulation with GUID %s is supported", BG_GUID);
        return NULL;
    }
    bg_instance *in = (bg_instance *)functions->allocateMemory(1, sizeof(bg_instance));
    if (in == NULL) return NULL;
    in->cb = *functions;
    in->name = name;
    bg_reset(&in->m, 0.0);
    in->state = ST_INSTANTIATED;
    return in;
}

void fmi2FreeInstance(fmi2Component c) {
    if (c == NULL) return;
    fmi2CallbackFreeMemory release = INST->cb.freeMemory;
    release(c);
}

fmi2Status fmi2SetupExperiment(fmi2Component c, fmi2Boolean tolDefined, fmi2Real tol,
                               fmi2Real tStart, fmi2Boolean stopDefined, fmi2Real tStop) {
    (void)tolDefined; (void)tol; (void)stopDefined; (void)tStop;
    if (INST->state != ST_INSTANTIATED) return bg_fail(INST, fmi2Error, "fmi2SetupExperiment: wrong state");
    /* Keep parameters and inputs the environment may already have set. */
    double p[BG_SZ(BG_NP)], u[BG_SZ(BG_NU)];
    memcpy(p, INST->m.p, sizeof p);
    memcpy(u, INST->m.u, sizeof u);
    bg_reset(&INST->m, tStart);
    memcpy(INST->m.p, p, sizeof p);
    memcpy(INST->m.u, u, sizeof u);
    return fmi2OK;
}

fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    if (INST->state != ST_INSTANTIATED) return bg_fail(INST, fmi2Error, "fmi2EnterInitializationMode: wrong state");
    INST->state = ST_INIT;
    return fmi2OK;
}

fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    if (INST->state != ST_INIT) return bg_fail(INST, fmi2Error, "fmi2ExitInitializationMode: wrong state");
    /* J-EX8: the calculated parameters and starts from the parameters set before
       initialization, and a consistent start of the algebraic unknowns (bg_init). */
    if (bg_init(&INST->m) != 0)
        return bg_fail(INST, fmi2Error, "fmi2ExitInitializationMode: no consistent start for the parameters set (the algebraic equations did not converge, or a start value is not finite)");
    INST->state = ST_STEP;
    return fmi2OK;
}

fmi2Status fmi2Terminate(fmi2Component c) { INST->state = ST_TERMINATED; return fmi2OK; }

fmi2Status fmi2Reset(fmi2Component c) {
    bg_reset(&INST->m, 0.0);
    INST->state = ST_INSTANTIATED;
    return fmi2OK;
}

fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t n, fmi2Real value[]) {
    bg_model *m = &INST->m;
    bg_update_outputs(m);
    for (size_t i = 0; i < n; ++i) {
        fmi2ValueReference r = vr[i];
        if (r < BG_NY) value[i] = m->y[r];
        else if (r < BG_VR_P0 + BG_NP) value[i] = m->p[r - BG_VR_P0];
        else if (r < BG_VR_U0 + BG_NU) value[i] = m->u[r - BG_VR_U0];
        else return bg_fail(INST, fmi2Error, "fmi2GetReal: unknown value reference");
    }
    return fmi2OK;
}

fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t n, const fmi2Real value[]) {
    bg_model *m = &INST->m;
    for (size_t i = 0; i < n; ++i) {
        fmi2ValueReference r = vr[i];
        if (r >= BG_VR_U0 && r < BG_VR_U0 + BG_NU) {
            unsigned k = r - BG_VR_U0;
            if (!(value[i] >= bg_u_min[k] && value[i] <= bg_u_max[k]))
                return bg_range_fail(INST, "input", bg_u_name[k], value[i], bg_u_min[k], bg_u_max[k]);
            m->u[k] = value[i];
            continue;
        }
        if (r < BG_VR_P0 || r >= BG_VR_P0 + BG_NP)
            return bg_fail(INST, fmi2Error, "fmi2SetReal: not a parameter or an input");
        unsigned k = r - BG_VR_P0;
        if (bg_p_tunable[k] == 2)
            return bg_name_fail(INST, "fmi2SetReal: %s is a calculated parameter; it is computed at initialization and cannot be set", bg_p_name[k]);
        if (bg_p_tunable[k] != 1 && INST->state != ST_INSTANTIATED && INST->state != ST_INIT)
            return bg_name_fail(INST, "fmi2SetReal: %s is a fixed parameter; set it before fmi2ExitInitializationMode", bg_p_name[k]);
        if (!(value[i] >= bg_p_min[k] && value[i] <= bg_p_max[k]))
            return bg_range_fail(INST, "parameter", bg_p_name[k], value[i], bg_p_min[k], bg_p_max[k]);
        m->p[k] = value[i];
    }
    m->y_valid = 0;
    return fmi2OK;
}

fmi2Status fmi2DoStep(fmi2Component c, fmi2Real tc, fmi2Real h, fmi2Boolean noSetPrior) {
    (void)noSetPrior;
    bg_model *m = &INST->m;
    if (INST->state != ST_STEP) return bg_fail(INST, fmi2Error, "fmi2DoStep: wrong state");
    if (fabs(tc - m->t) > 1e-9 * (1.0 + fabs(tc)))
        return bg_fail(INST, fmi2Error, "fmi2DoStep: communication point does not match the FMU time");
    double steps = h / BG_DT;
    long long n = llround(steps);
    if (n < 0 || fabs(steps - (double)n) > 1e-6)
        return bg_fail(INST, fmi2Error, "fmi2DoStep: h must be a whole multiple of the internal step");
    for (long long i = 0; i < n; ++i) {
        int rc = bg_step(m);
        if (rc == 0) continue;
        if (rc < 0) return bg_fail(INST, fmi2Error, "fmi2DoStep: the state became non-finite or the iteration matrix is singular");
#if BG_NMON > 0
        /* A StopSimulation block ends the run (fmi2Discard, fmi2Terminated reads true; the
           outputs at the stop time stay readable); a failed Assertion is an error. */
        const char *who = bg_monitor_name[m->monitor - 1];
        if (rc == BG_STEP_STOP) {
            if (INST->cb.logger != NULL)
                INST->cb.logger(INST->cb.componentEnvironment, INST->name, fmi2Discard, "terminate",
                                "the run was stopped by %s at t = %g", who, m->t);
            INST->state = ST_TERMINATED;
            return fmi2Discard;
        }
        if (INST->cb.logger != NULL)
            INST->cb.logger(INST->cb.componentEnvironment, INST->name, fmi2Error, "error",
                            "assertion %s failed at t = %g", who, m->t);
        INST->state = ST_ERROR;
        return fmi2Error;
#endif
    }
    return fmi2OK;
}

/* Unsupported or trivial parts of the interface. */
fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t n, fmi2Integer v[]) { (void)vr; (void)v; return n ? bg_fail(INST, fmi2Error, "no Integer variables") : fmi2OK; }
fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t n, fmi2Boolean v[]) { (void)vr; (void)v; return n ? bg_fail(INST, fmi2Error, "no Boolean variables") : fmi2OK; }
fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t n, fmi2String v[]) { (void)vr; (void)v; return n ? bg_fail(INST, fmi2Error, "no String variables") : fmi2OK; }
fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t n, const fmi2Integer v[]) { (void)vr; (void)v; return n ? bg_fail(INST, fmi2Error, "no Integer variables") : fmi2OK; }
fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t n, const fmi2Boolean v[]) { (void)vr; (void)v; return n ? bg_fail(INST, fmi2Error, "no Boolean variables") : fmi2OK; }
fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t n, const fmi2String v[]) { (void)vr; (void)v; return n ? bg_fail(INST, fmi2Error, "no String variables") : fmi2OK; }
fmi2Status fmi2GetFMUstate(fmi2Component c, fmi2FMUstate *s) { (void)s; return bg_fail(INST, fmi2Error, "FMU state not supported"); }
fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate s) { (void)s; return bg_fail(INST, fmi2Error, "FMU state not supported"); }
fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate *s) { (void)s; return bg_fail(INST, fmi2Error, "FMU state not supported"); }
fmi2Status fmi2SerializedFMUstateSize(fmi2Component c, fmi2FMUstate s, size_t *n) { (void)s; (void)n; return bg_fail(INST, fmi2Error, "FMU state not supported"); }
fmi2Status fmi2SerializeFMUstate(fmi2Component c, fmi2FMUstate s, fmi2Byte b[], size_t n) { (void)s; (void)b; (void)n; return bg_fail(INST, fmi2Error, "FMU state not supported"); }
fmi2Status fmi2DeSerializeFMUstate(fmi2Component c, const fmi2Byte b[], size_t n, fmi2FMUstate *s) { (void)b; (void)n; (void)s; return bg_fail(INST, fmi2Error, "FMU state not supported"); }
fmi2Status fmi2GetDirectionalDerivative(fmi2Component c, const fmi2ValueReference u[], size_t nu, const fmi2ValueReference z[], size_t nz, const fmi2Real dv[], fmi2Real dz[]) { (void)u; (void)nu; (void)z; (void)nz; (void)dv; (void)dz; return bg_fail(INST, fmi2Error, "directional derivatives not supported"); }
fmi2Status fmi2SetRealInputDerivatives(fmi2Component c, const fmi2ValueReference vr[], size_t n, const fmi2Integer o[], const fmi2Real v[]) { (void)vr; (void)o; (void)v; return n ? bg_fail(INST, fmi2Error, "inputs are held constant over a step; input derivatives are not supported") : fmi2OK; }
fmi2Status fmi2GetRealOutputDerivatives(fmi2Component c, const fmi2ValueReference vr[], size_t n, const fmi2Integer o[], fmi2Real v[]) { (void)vr; (void)o; (void)v; return n ? bg_fail(INST, fmi2Error, "output derivatives not supported") : fmi2OK; }
fmi2Status fmi2CancelStep(fmi2Component c) { return bg_fail(INST, fmi2Error, "fmi2CancelStep: steps are synchronous"); }
fmi2Status fmi2GetStatus(fmi2Component c, const fmi2StatusKind k, fmi2Status *v) { (void)k; (void)v; return bg_fail(INST, fmi2Discard, "fmi2GetStatus: not supported"); }
fmi2Status fmi2GetRealStatus(fmi2Component c, const fmi2StatusKind k, fmi2Real *v) {
    if (k == fmi2LastSuccessfulTime) { *v = INST->m.t; return fmi2OK; }
    return bg_fail(INST, fmi2Discard, "fmi2GetRealStatus: not supported");
}
fmi2Status fmi2GetIntegerStatus(fmi2Component c, const fmi2StatusKind k, fmi2Integer *v) { (void)k; (void)v; return bg_fail(INST, fmi2Discard, "not supported"); }
fmi2Status fmi2GetBooleanStatus(fmi2Component c, const fmi2StatusKind k, fmi2Boolean *v) {
    if (k == fmi2Terminated) { *v = INST->state == ST_TERMINATED ? fmi2True : fmi2False; return fmi2OK; }
    return bg_fail(INST, fmi2Discard, "fmi2GetBooleanStatus: not supported");
}
fmi2Status fmi2GetStringStatus(fmi2Component c, const fmi2StatusKind k, fmi2String *v) { (void)k; (void)v; return bg_fail(INST, fmi2Discard, "not supported"); }
