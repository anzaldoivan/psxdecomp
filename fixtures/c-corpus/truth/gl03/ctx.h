typedef struct GameState {
    /* 0x00 */ s32 frame;
    /* 0x04 */ s32 mode;
    /* 0x08 */ u16 pad;
    /* 0x0A */ u16 padPrev;
} GameState;

extern GameState g_Game;
