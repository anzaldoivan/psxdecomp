// twin: struct-def
#include "common.h"

typedef struct MyVec {
    s16 x;
    s16 y;
} MyVec;

typedef struct MyActor {
    MyVec pos;
    MyVec vel;
    u8 state;
    u8 flags;
    s16 hp;
    struct MyActor *target;
} MyActor;

extern s32 func_8003C1D0(MyActor *a);

void func_80034F30(MyVec *out, MyActor *a, s16 dx) {
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
