// class: calls
// func: func_800B3680
// canary: ccorpus-e5c3b1074a98
#include "common.h"
#include "ctx.h"

s32 func_800B3680(Item *it) {
    if (it->count < 0) {
        return 0;
    }
    return func_8003C1D0(it->count + 4);
}
