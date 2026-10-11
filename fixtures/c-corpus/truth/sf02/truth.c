// class: struct-fields
// func: func_80031C00
// canary: ccorpus-9eede78cc6ab
#include "common.h"
#include "ctx.h"

s32 func_80031C00(Door *d, s16 px, s16 py) {
    if (px < d->box.min.x || px > d->box.max.x) {
        return 0;
    }
    if (py < d->box.min.y || py > d->box.max.y) {
        return 0;
    }
    d->open = 1;
    d->timer = 30;
    return 1;
}
