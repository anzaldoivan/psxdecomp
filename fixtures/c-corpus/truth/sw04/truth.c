// class: switch
// func: func_800B31E0
// canary: ccorpus-b25c70e8941f
#include "common.h"
#include "ctx.h"

s32 func_800B31E0(Item *it, s32 dir) {
    switch (dir) {
    case 0:
        return it->price;
    case 1:
        return it->price + it->count;
    case 2:
        return it->price - it->count;
    case 3:
        return -it->price;
    }
    return 0;
}
