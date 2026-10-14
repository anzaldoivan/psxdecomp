// twin: register-pin
// compilers: gcc2.95.2
#include "common.h"
#include "ctx.h"

s32 func_800B3350(s32 a, s32 b) {
    register s32 t asm("$5") = a * 3 + b;

    if (t > 100) {
        t = 100;
    }
    g_Game.mode = t;
    return t - a;
}
