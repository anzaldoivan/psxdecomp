// class: odd
// func: func_800B3790
// canary: ccorpus-95f8b02c6e17
#include "common.h"
#include "ctx.h"

s32 func_800B3790(Item *it, s32 hit) {
    if (it->flags & 1) {
        func_8003C1D0(it->count);
    }
    if (it->flags & 1) {
        it->count -= hit;
    }
    if (it->count < 0) {
        it->count = 0;
    }
    return it->count;
}
