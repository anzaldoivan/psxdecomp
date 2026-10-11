// class: signedness
// func: func_80053C30
// canary: ccorpus-c5713d9e9687
#include "common.h"
#include "ctx.h"

s32 func_80053C30(u32 *src, s32 n) {
    s32 sum = 0;
    s32 i;

    for (i = 0; i < n; i++) {
        sum += (s32)(src[i] << 8) >> 8;
    }
    return sum;
}
