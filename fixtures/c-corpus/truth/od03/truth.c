// class: odd
// func: func_800B3750
// canary: ccorpus-c41a7e3b92d6
#include "common.h"
#include "ctx.h"

void func_800B3750(Item *it, s32 step) {
    g_Cursor = it->slot;
    it->slot = it->slot + step;
    g_Cursor = it->slot + 1;
    it->timer = 8;
}
