// class: divmul
// func: func_800B3560
// canary: ccorpus-f92b4d71a086
#include "common.h"
#include "ctx.h"

void func_800B3560(Vec3 *v, s32 scale) {
    v->x = (v->x * scale) >> 12;
    v->y = (v->y * scale) >> 12;
    v->z = ((v->z * scale) + 0x800) >> 12;
}
