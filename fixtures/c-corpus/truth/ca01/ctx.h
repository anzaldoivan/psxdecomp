typedef struct Item {
    /* 0x00 */ u8 kind;
    /* 0x01 */ u8 flags;
    /* 0x02 */ s16 count;
    /* 0x04 */ s32 price;
    /* 0x08 */ s16 slot;
    /* 0x0A */ s16 timer;
} Item;

extern s32 func_8003C1D0(s32 a);
