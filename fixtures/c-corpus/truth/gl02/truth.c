// class: globals
// func: func_800B3300
// canary: ccorpus-91e2d6b40a3c
#include "common.h"
#include "ctx.h"

s32 func_800B3300(s32 idx, s32 delta) {
    s32 old;

    if (idx >= 16) {
        return -1;
    }
    old = g_Scores[idx];
    g_Scores[idx] = old + delta;
    g_ScoreSum += delta;
    if (g_Scores[idx] > g_Best) {
        g_Best = g_Scores[idx];
    }
    return old;
}
