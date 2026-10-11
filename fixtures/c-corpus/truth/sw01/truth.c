// class: switch
// func: func_800B3100
// canary: ccorpus-7a3f19c2b6d4
#include "common.h"
#include "ctx.h"

s32 func_800B3100(Item *it) {
    u8 k = it->kind;

    if (k == 1) {
        return it->price + 10;
    } else if (k == 2) {
        return it->price * 2;
    } else if (k == 5) {
        return it->price >> 1;
    } else if (k == 7) {
        return it->price - it->count;
    } else if (k == 9) {
        return it->count << 3;
    }
    return 0;
}
