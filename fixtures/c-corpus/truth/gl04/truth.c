// class: globals
// func: func_800B33A0
// canary: ccorpus-c6b3e8052f14
#include "common.h"
#include "ctx.h"

u32 func_800B33A0(u32 bit, s32 shift) {
    u32 stat = g_SpadFlags;

    if (stat == 0) {
        return 0xFF;
    }
    return ((stat & bit) >> shift) + 1;
}
