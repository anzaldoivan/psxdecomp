// class: loops
// func: func_80065F30
// canary: ccorpus-9ec43a91ecc8
#include "common.h"
#include "ctx.h"

s32 func_80065F30(Grid *g, u8 val) {
    s32 x;
    s32 y;
    s32 n = 0;

    for (y = 0; y < 4; y++) {
        for (x = 0; x < 6; x++) {
            if (g->cell[y][x] == val) {
                g->cell[y][x] = 0;
                n++;
            }
        }
    }
    return n;
}
