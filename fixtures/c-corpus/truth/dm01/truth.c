// class: divmul
// func: func_800B3440
// canary: ccorpus-d80c35a79b26
#include "common.h"
#include "ctx.h"

s32 func_800B3440(Actor *a, s32 total) {
    s32 share = total / 10;

    a->hp += share;
    return total - share * 10;
}
