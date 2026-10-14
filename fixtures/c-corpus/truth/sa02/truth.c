// class: struct-absent
// func: func_80042B10
// canary: ccorpus-5671f2b02d20
#include "common.h"
#include "ctx.h"
#include "hidden.h"

s32 func_80042B10(Timer *t, s32 dt) {
    t->elapsed += dt;
    if (t->elapsed >= t->period) {
        t->elapsed -= t->period;
        t->ticks++;
        return 1;
    }
    return 0;
}
