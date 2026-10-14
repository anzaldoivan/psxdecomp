// class: loops
// func: func_80061B10
// canary: ccorpus-4c13ef8c33e8
#include "common.h"
#include "ctx.h"

s32 func_80061B10(s32 thresh) {
    s32 i;
    s32 count = 0;

    for (i = 0; i < 32; i++) {
        if (g_Samples[i] > thresh) {
            count++;
        }
    }
    return count;
}
