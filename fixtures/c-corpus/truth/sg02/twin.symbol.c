// twin: symbol
#include "common.h"
#include "ctx.h"

extern u8 D_800A5400;
extern s32 D_800A5404;

void func_80052B20(void) {
    D_800A5400++;
    if (D_800A5400 == 0) {
        D_800A5404++;
    }
}
