// twin: symbol
#include "common.h"
#include "ctx.h"

extern s32 D_800A4C04;

s32 func_800B3350(s32 a, s32 b) {
    s32 t = a * 3 + b;

    if (t > 100) {
        t = 100;
    }
    D_800A4C04 = t;
    return t - a;
}
