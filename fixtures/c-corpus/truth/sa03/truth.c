// class: struct-absent
// func: func_80043C20
// canary: ccorpus-4b94925c292d
#include "common.h"
#include "ctx.h"
#include "hidden.h"

void func_80043C20(Menu *m, s32 dir) {
    m->cursor += dir;
    if (m->cursor < 0) {
        m->cursor = m->count - 1;
    }
    if (m->cursor >= m->count) {
        m->cursor = 0;
    }
    m->dirty = 1;
    if (m->items != NULL) {
        func_8003D410(m);
    }
}
