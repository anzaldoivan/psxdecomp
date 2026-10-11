struct Menu {
    /* 0x00 */ s16 cursor;
    /* 0x02 */ s16 count;
    /* 0x04 */ u8 dirty;
    /* 0x05 */ u8 pad[3];
    /* 0x08 */ void *items;
};
