// twin: offset-cast
#include "common.h"
#include "ctx.h"

s32 func_80031C00(Door *d, s16 px, s16 py) {
    if (px < *(s16 *)((u8 *)d + 0) || px > *(s16 *)((u8 *)d + 4)) {
        return 0;
    }
    if (py < *(s16 *)((u8 *)d + 2) || py > *(s16 *)((u8 *)d + 6)) {
        return 0;
    }
    *(u8 *)((u8 *)d + 0xA) = 1;
    *(s16 *)((u8 *)d + 8) = 30;
    return 1;
}
