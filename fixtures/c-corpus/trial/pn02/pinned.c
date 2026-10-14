// trial: register-pin, a declaration with no type
// func: func_800B4A60
// canary: ccorpus-91c4e27d05ab
// needs: pin:$18:a
// spare: pin:$16:b
#include "common.h"
#include "ctx.h"

s32 func_800B4A60(s32 x, s32 y) {
    register s32 a asm("$18") = func_8003C1D0(x);
    register b asm("$16") = func_8003C1D0(y);

    return func_8003C1D0(a + b) + a - b;
}
