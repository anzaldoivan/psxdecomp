// trial: register-pin
// func: func_800B4A10
// canary: ccorpus-3d81e06fb27a
// needs: pin:$18:a
// spare: pin:$16:b
#include "common.h"
#include "ctx.h"

s32 func_800B4A10(s32 x, s32 y) {
    register s32 a asm("$18") = func_8003C1D0(x);
    register s32 b asm("$16") = func_8003C1D0(y);

    return func_8003C1D0(a + b) + a - b;
}
