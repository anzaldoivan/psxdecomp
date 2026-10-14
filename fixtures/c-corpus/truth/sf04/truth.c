// class: struct-fields
// func: func_80033E20
// canary: ccorpus-22f3e23af91b
#include "common.h"
#include "ctx.h"

s32 func_80033E20(Actor *self) {
    if (self->target == NULL) {
        return 0;
    }
    self->vel.x = (self->target->pos.x - self->pos.x) >> 3;
    self->vel.y = (self->target->pos.y - self->pos.y) >> 3;
    if (self->vel.x == 0 && self->vel.y == 0) {
        self->state = 2;
    }
    return 1;
}
