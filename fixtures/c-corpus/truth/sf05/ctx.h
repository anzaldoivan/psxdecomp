typedef struct Vec2 {
    s16 x;
    s16 y;
} Vec2;

typedef struct Actor {
    /* 0x00 */ Vec2 pos;
    /* 0x04 */ Vec2 vel;
    /* 0x08 */ u8 state;
    /* 0x09 */ u8 flags;
    /* 0x0A */ s16 hp;
    /* 0x0C */ struct Actor *target;
} Actor;
extern s32 func_8003C1D0(Actor *a);
