// class: globals
// func: func_800B33F0
// canary: ccorpus-2a94d7f6b0e1
#include "common.h"
#include "ctx.h"

s32 func_800B33F0(s32 a, s32 b) {
    s32 base = g_SpadWork[2];

    if (base > a) {
        return base - b;
    }
    return a + b * 3;
}
