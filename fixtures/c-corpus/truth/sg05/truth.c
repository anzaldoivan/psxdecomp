// class: signedness
// func: func_80055E50
// canary: ccorpus-660e12805739
#include "common.h"
#include "ctx.h"

s32 func_80055E50(s32 a, u32 b, s32 lo) {
    if ((u32)(a - lo) < b) {
        return a / 4;
    }
    if (a > g_Limit) {
        return (u32)a / 8;
    }
    if (a < lo) {
        return a / 2 + lo;
    }
    return a;
}
