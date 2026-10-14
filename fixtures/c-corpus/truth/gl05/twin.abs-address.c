// twin: abs-address
// compilers: gcc2.7.2
#include "common.h"
#include "ctx.h"

#define g_SpadWork ((s32 *)0x1F800010)

s32 func_800B33F0(s32 a, s32 b) {
    s32 base = g_SpadWork[2];

    if (base > a) {
        return base - b;
    }
    return a + b * 3;
}
