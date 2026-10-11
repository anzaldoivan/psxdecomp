// class: odd
// func: func_800B3710
// canary: ccorpus-7d02f6a9e5b3
#include "common.h"
#include "ctx.h"

s32 func_800B3710(Item *it, s32 a, s32 b) {
    if (a - b > 0) {
        it->slot = a - b;
        return 1;
    }
    it->slot = 0;
    return 0;
}
