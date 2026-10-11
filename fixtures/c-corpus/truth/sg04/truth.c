// class: signedness
// func: func_80054D40
// canary: ccorpus-0e3b0311fc86
#include "common.h"
#include "ctx.h"

void func_80054D40(Actor *a, s32 idx) {
    a->pos.x += g_DeltaTab[idx & 15];
    a->pos.y += g_DeltaTab[(idx + 4) & 15];
    a->vel.x = g_DeltaTab[(idx + 8) & 15];
    a->vel.y = g_DeltaTab[(idx + 12) & 15];
}
