// class: switch
// func: func_800B3140
// canary: ccorpus-e41b82d05a97
#include "common.h"
#include "ctx.h"

s32 func_800B3140(Item *it, s32 cmd) {
    switch (cmd) {
    case 0:
        it->slot = 1;
        break;
    case 3:
        it->slot = 2;
        it->timer = 0;
        break;
    case 9:
        it->slot = 4;
        break;
    case 12:
        it->slot = 5;
        it->timer = 30;
        break;
    }
    return it->slot;
}
