// twin: offset-cast
#include "common.h"
#include "ctx.h"

void func_800B35F0(Item *it) {
    if (*(u8 *)((u8 *)it + 1) & 2) {
        func_8003C1E8(3);
    }
    *(s16 *)((u8 *)it + 10) = 0;
    *(s16 *)((u8 *)it + 8) = 1;
}
