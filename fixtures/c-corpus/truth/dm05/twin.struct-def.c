// twin: struct-def
#include "common.h"
#include "ctx.h"

struct V3 {
    s32 x;
    s32 y;
    s32 z;
};

void func_800B3560(struct V3 *v, s32 scale) {
    v->x = (v->x * scale) >> 12;
    v->y = (v->y * scale) >> 12;
    v->z = ((v->z * scale) + 0x800) >> 12;
}
