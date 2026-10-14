// class: odd
// func: func_800B37D0
// canary: ccorpus-0a5d83e1b7c9
#include "common.h"
#include "ctx.h"

void func_800B37D0(Item *it) {
    s32 i;

    for (i = 0; i <= 8; i++) { //! @bug g_Slots has eight entries, the last write lands past the array
        g_Slots[i] = it->count + i;
    }
}
