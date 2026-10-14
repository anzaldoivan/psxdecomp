// class: divmul
// func: func_800B3520
// canary: ccorpus-67c0f1a2d3e9
#include "common.h"
#include "ctx.h"

s32 func_800B3520(Actor *a, s32 row, s32 col) {
    s32 cell = row * 36 + col * 10;

    a->x = cell;
    a->mp = cell * 24 + row;
    return cell + a->y * 7;
}
