// twin: goto
#include "common.h"
#include "ctx.h"

s32 func_800B3230(Item *it, s32 score) {
    s32 grade;

    if (score >= 90) {
        grade = 3;
        goto check;
    }
    if (score >= 60) {
        grade = 2;
        goto check;
    }
    if (score > 0) {
        grade = 1;
        goto check;
    }
    grade = 0;
check:
    if (grade > it->slot) {
        it->slot = grade;
        it->timer = 30;
    }
    return grade;
}
