// class: odd
// func: func_800B36C0
// canary: ccorpus-3b6e90d2c481
#include "common.h"
#include "ctx.h"

s32 func_800B36C0(Item *it, s32 bonus) {
    it->count = bonus + 5;
    g_Tick += 2;
    if (it->count > 20) {
        it->count = 20;
    }
    return it->count;
}
