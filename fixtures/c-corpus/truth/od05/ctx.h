typedef struct Item {
    /* 0x00 */ u8 kind;
    /* 0x01 */ u8 flags;
    /* 0x02 */ s16 count;
} Item;

extern s16 g_Slots[8];
