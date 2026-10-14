// class: signedness
// func: func_80051A10
// canary: ccorpus-f6ba8c3af131
#include "common.h"
#include "ctx.h"

s32 func_80051A10(Gauge *g) {
    if (g_PadHeld & 0x40) {
        return -1;
    }
    if (g->cur < g->max) {
        return g->max - g->cur;
    }
    return 0;
}
