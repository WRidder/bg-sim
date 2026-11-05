/* The browser's side of the FMU: one instance from a static arena, no libc I/O. */
#include <stddef.h>
#include <string.h>
#include "fmi2Functions.h"

#define ARENA (1 << 20)
static _Alignas(16) unsigned char arena[ARENA];
static size_t used;

static void *arena_alloc(size_t n, size_t size) {
  size_t bytes = (n * size + 15) & ~(size_t)15;
  if (used + bytes > ARENA) return NULL;
  void *p = arena + used;
  used += bytes;
  memset(p, 0, bytes);
  return p;
}
static void arena_free(void *p) { (void)p; }
static void quiet(fmi2ComponentEnvironment e, fmi2String i, fmi2Status s, fmi2String c, fmi2String m, ...) {
  (void)e; (void)i; (void)s; (void)c; (void)m;
}

static fmi2CallbackFunctions callbacks = {quiet, arena_alloc, arena_free, NULL, NULL};
static fmi2Component self;
static double buffer[256];
static fmi2ValueReference refs[256];
static char text[128];

__attribute__((export_name("sim_text"))) char *sim_text(void) { return text; }
__attribute__((export_name("sim_buffer"))) double *sim_buffer(void) { return buffer; }
__attribute__((export_name("sim_refs"))) unsigned *sim_refs(void) { return refs; }
__attribute__((export_name("sim_instantiate")))
int sim_instantiate(void) {
  used = 0;
  self = fmi2Instantiate("sim", fmi2CoSimulation, text, "", &callbacks, fmi2False, fmi2False);
  return self != NULL;
}
__attribute__((export_name("sim_set"))) int sim_set(int n) { return fmi2SetReal(self, refs, n, buffer); }
__attribute__((export_name("sim_get"))) int sim_get(int n) { return fmi2GetReal(self, refs, n, buffer); }
__attribute__((export_name("sim_start"))) int sim_start(void) {
  if (fmi2SetupExperiment(self, fmi2False, 0.0, 0.0, fmi2False, 0.0) > fmi2Warning) return 0;
  if (fmi2EnterInitializationMode(self) > fmi2Warning) return 0;
  return fmi2ExitInitializationMode(self) <= fmi2Warning;
}
__attribute__((export_name("sim_step"))) int sim_step(double t, double h) { return fmi2DoStep(self, t, h, fmi2True); }
