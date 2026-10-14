// class: globals
// func: func_80034B18
// canary: ccorpus-0c8f42d6e1a7
#include "common.h"
#include "ctx.h"

u32 func_80034B18(u32 mask) {
    u32 pressed;

    pressed = g_Game.pad & ~g_Game.padPrev;
    g_Game.padPrev = g_Game.pad;
    if (g_Game.mode == 2) {
        I_STAT = mask;
    }
    g_Game.frame++;
    return pressed & mask;
}
