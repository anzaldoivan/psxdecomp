// class: divmul
// func: func_800B3480
// canary: ccorpus-4e1fb9830c75
#include "common.h"
#include "ctx.h"

s32 func_800B3480(Actor *a, s32 frames) {
    s32 sec = (frames / 60) % 60;

    a->mp = sec;
    return sec * 100 + frames % 60;
}
