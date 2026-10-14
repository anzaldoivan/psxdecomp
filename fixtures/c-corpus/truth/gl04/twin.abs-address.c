// twin: abs-address
#include "common.h"
#include "ctx.h"

#define g_SpadFlags (*(volatile u32 *)0x1F800000)

u32 func_800B33A0(u32 bit, s32 shift) {
    u32 stat = g_SpadFlags;

    if (stat == 0) {
        return 0xFF;
    }
    return ((stat & bit) >> shift) + 1;
}
