typedef struct GameState {
    /* 0x00 */ s32 frame;
    /* 0x04 */ s32 mode;
    /* 0x08 */ u16 pad;
    /* 0x0A */ u16 padPrev;
} GameState;

extern GameState g_Game;
extern s32 D_800A4C10;
extern volatile u32 I_STAT;
