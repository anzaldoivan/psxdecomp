// class: struct-fields
// func: func_80032D10
// canary: ccorpus-445bcb26f52a
#include "common.h"
#include "ctx.h"

s32 func_80032D10(Pack *p, s16 id) {
    s32 i;

    for (i = 0; i < 8; i++) {
        if (p->slots[i].id == id) {
            p->slots[i].count += 1;
            p->slots[i].flags |= 1;
            return i;
        }
        if (p->slots[i].count == 0) {
            p->slots[i].id = id;
            p->slots[i].count = 1;
            return i;
        }
    }
    p->gold -= 5;
    return -1;
}
