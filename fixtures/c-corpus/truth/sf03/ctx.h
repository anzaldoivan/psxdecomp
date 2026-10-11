typedef struct Slot {
    /* 0x00 */ s16 id;
    /* 0x02 */ s16 count;
    /* 0x04 */ u8 flags;
    /* 0x05 */ u8 pad[3];
} Slot;

typedef struct Pack {
    /* 0x00 */ Slot slots[8];
    /* 0x40 */ s32 gold;
} Pack;
