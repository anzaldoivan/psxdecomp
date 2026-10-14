// class: loops
// func: func_80064E20
// canary: ccorpus-dbfa066e6359
#include "common.h"
#include "ctx.h"

s32 func_80064E20(s32 *dst, s32 v, s32 n) {
    s32 sum = 0;

    do {
        *dst++ = v;
        sum += v;
        v += 4;
    } while (--n > 0);
    return sum;
}
