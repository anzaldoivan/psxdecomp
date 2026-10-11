// class: calls
// func: func_800B3630
// canary: ccorpus-19d4a8e6f573
#include "common.h"
#include "ctx.h"

s32 func_800B3630(Item *it, s32 n) {
    s32 a = func_8003C1D0(n);
    s32 b = func_8003C200(a + n, it->count);

    it->price = a;
    it->timer = func_8003C1D0(b);
    return b + n;
}
