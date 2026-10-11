// twin: symbol
#include "common.h"
#include "ctx.h"

u32 func_80034B18(u32 mask) {
    u32 pressed;

    pressed = g_Game.pad & ~g_Game.padPrev;
    g_Game.padPrev = g_Game.pad;
    if (g_Game.mode == 2) {
        D_800A4C10 = mask;
    }
    g_Game.frame++;
    return pressed & mask;
}
