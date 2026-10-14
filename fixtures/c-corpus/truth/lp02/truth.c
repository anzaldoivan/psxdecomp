// class: loops
// func: func_80062C20
// canary: ccorpus-446bc15087f4
#include "common.h"
#include "ctx.h"

s32 func_80062C20(Entry *tab, s32 n, s16 key) {
    s32 i;

    for (i = n - 1; i >= 0; i--) {
        if (tab[i].key == key) {
            return tab[i].val;
        }
    }
    return -1;
}
