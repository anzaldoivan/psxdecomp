// class: signedness
// func: func_80052B20
// canary: ccorpus-60a5ea925a97
#include "common.h"
#include "ctx.h"

void func_80052B20(void) {
    g_FrameTick++;
    if (g_FrameTick == 0) {
        g_Wraps++;
    }
}
