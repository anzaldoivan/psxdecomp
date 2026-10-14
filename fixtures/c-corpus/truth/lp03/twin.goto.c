// twin: goto
#include "common.h"
#include "ctx.h"

s32 func_80063D10(u8 *p, s32 max) {
    s32 n = 0;

    while (n < max && p[n] != 0xFF) {
        goto next;
next:
        n++;
    }
    return n;
}
