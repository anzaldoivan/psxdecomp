// twin: goto
#include "common.h"
#include "ctx.h"

s32 func_800B3680(Item *it) {
    if (it->count < 0) {
        goto zero;
    }
    return func_8003C1D0(it->count + 4);
zero:
    return 0;
}
