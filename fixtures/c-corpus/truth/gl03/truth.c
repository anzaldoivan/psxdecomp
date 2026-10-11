// class: globals
// func: func_800B3350
// canary: ccorpus-5f07a1c9e83d
#include "common.h"
#include "ctx.h"

s32 func_800B3350(s32 a, s32 b) {
    s32 t = a * 3 + b;

    if (t > 100) {
        t = 100;
    }
    g_Game.mode = t;
    return t - a;
}
