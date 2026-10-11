// class: struct-fields
// func: func_80021A40
// canary: ccorpus-5d1e0b7a93c4
#include "common.h"
#include "ctx.h"

s32 func_80021A40(Actor *self, s32 amount) {
    if (self->flags & 4) {
        return 0;
    }
    self->hp -= amount;
    if (self->hp <= 0) {
        self->hp = 0;
        self->state = 3;
        return 1;
    }
    return 0;
}
