// class: switch
// func: func_800B3230
// canary: ccorpus-3c8ad147f0b2
#include "common.h"
#include "ctx.h"

s32 func_800B3230(Item *it, s32 score) {
    s32 grade;

    if (score >= 90) {
        grade = 3;
    } else if (score >= 60) {
        grade = 2;
    } else if (score > 0) {
        grade = 1;
    } else {
        grade = 0;
    }
    if (grade > it->slot) {
        it->slot = grade;
        it->timer = 30;
    }
    return grade;
}
