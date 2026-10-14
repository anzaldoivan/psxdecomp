// class: struct-fields
// func: func_80034F30
// canary: ccorpus-f20c7392dd4a
#include "common.h"
#include "ctx.h"

void func_80034F30(Vec2 *out, Actor *a, s16 dx) {
    out->x = a->pos.x + dx;
    out->y = a->pos.y;
    a->flags |= 0x10;
    if (a->flags & 0x80) {
        func_8003C1D0(a);
        a->flags &= ~0x80;
    }
    if (a->hp < dx) {
        a->state = 4;
    }
}
