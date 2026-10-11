// twin: register-pin
#include "common.h"
#include "ctx.h"

s32 func_80061B10(s32 thresh) {
    s32 i;
    register s32 count asm("$6");

    count = 0;
    for (i = 0; i < 32; i++) {
        if (g_Samples[i] > thresh) {
            count++;
        }
    }
    return count;
}
