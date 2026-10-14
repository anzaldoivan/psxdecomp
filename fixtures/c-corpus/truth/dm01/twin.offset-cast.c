// twin: offset-cast
#include "common.h"
#include "ctx.h"

s32 func_800B3440(Actor *a, s32 total) {
    s32 share = total / 10;

    *(s16 *)((u8 *)a + 4) += share;
    return total - share * 10;
}
