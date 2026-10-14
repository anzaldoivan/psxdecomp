// class: switch
// func: func_800B3190
// canary: ccorpus-0d96f5a3c718
#include "common.h"
#include "ctx.h"

s32 func_800B3190(Item *it, s32 level) {
    s32 bonus = 0;

    switch (level) {
    case 4:
        bonus += 8;
    case 3:
        bonus += 4;
    case 2:
        bonus += 2;
    case 1:
        bonus += 1;
        break;
    default:
        return -1;
    }
    it->count += bonus;
    it->timer = bonus * 2;
    return bonus;
}
