// class: calls
// func: func_800B35B0
// canary: ccorpus-08e7c4b5a132
#include "common.h"
#include "ctx.h"

s32 func_800B35B0(Item *it) {
    s32 r = func_8003C1D0(it->count + 1);

    if (r < 0) {
        it->timer = 0;
    }
    it->price = r;
    return r;
}
