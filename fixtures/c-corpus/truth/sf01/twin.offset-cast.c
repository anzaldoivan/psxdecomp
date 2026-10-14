// twin: offset-cast
#include "common.h"
#include "ctx.h"

s32 func_80021A40(Actor *self, s32 amount) {
    if (*(u8 *)((u8 *)self + 9) & 4) {
        return 0;
    }
    *(s16 *)((u8 *)self + 0xA) -= amount;
    if (*(s16 *)((u8 *)self + 0xA) <= 0) {
        *(s16 *)((u8 *)self + 0xA) = 0;
        *(u8 *)((u8 *)self + 8) = 3;
        return 1;
    }
    return 0;
}
