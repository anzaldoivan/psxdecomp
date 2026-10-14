typedef struct Vec2 {
    s16 x;
    s16 y;
} Vec2;

typedef struct Rect {
    /* 0x00 */ Vec2 min;
    /* 0x04 */ Vec2 max;
} Rect;

typedef struct Door {
    /* 0x00 */ Rect box;
    /* 0x08 */ s16 timer;
    /* 0x0A */ u8 open;
    /* 0x0B */ u8 pad;
} Door;
