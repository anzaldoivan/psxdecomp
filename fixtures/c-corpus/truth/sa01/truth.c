// class: struct-absent
// func: func_80041A00
// canary: ccorpus-7f17f1aef293
#include "common.h"
#include "ctx.h"
#include "hidden.h"

s32 func_80041A00(Particle *p) {
    p->x += p->vx;
    p->life -= 1;
    if (p->life < 0) {
        p->kind = 0;
        return 1;
    }
    return 0;
}
