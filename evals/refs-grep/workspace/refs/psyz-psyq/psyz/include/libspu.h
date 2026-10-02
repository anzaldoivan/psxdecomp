/* eval fixture: a declaration list written for psxdecomp's refs-grep case (names only) */
#ifndef LIBSPU_H
#define LIBSPU_H
void SpuInit(void);
void SpuSetKey(long on_off, unsigned long voice_bit);
void SpuSetVoiceVolume(int v, short l, short r);
#endif
