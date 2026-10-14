// class: divmul
// func: func_800B34D0
// canary: ccorpus-a3d56e20f98b
#include "common.h"
#include "ctx.h"

s32 func_800B34D0(Actor *a, s32 total, s32 count) {
    if (count == 0) {
        return 0;
    }
    a->x = total / count + 1;
    a->y = total % count;
    return total / count;
}
