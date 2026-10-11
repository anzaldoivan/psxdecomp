// twin: abs-address
// compilers: gcc2.7.2
#include "common.h"
#include "ctx.h"

#define g_PadHeldX (*(u16 *)0x1F800020)

s32 func_80051A10(Gauge *g) {
    if (g_PadHeldX & 0x40) {
        return -1;
    }
    if (g->cur < g->max) {
        return g->max - g->cur;
    }
    return 0;
}
