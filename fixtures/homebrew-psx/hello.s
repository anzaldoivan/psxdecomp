# hello.s — psxdecomp's synthetic PS1 target (CC0 1.0; written for this repository, no game bytes).
# Two functions and two PsyQ-shaped library stamps. make_disc.py carries the same words pre-encoded so tier 1 needs no
# assembler; tier 1b assembles this file in the profile container and asserts the bytes are equal (smoke/Makefile).
    .set noreorder
    .set noat
    .text
    .globl _start
_start:                         # 0x80010000
    addiu   $sp, $sp, -24
    sw      $ra, 20($sp)
    addiu   $t0, $zero, 42
spin:
    beq     $zero, $zero, spin
    nop
    .globl leaf
leaf:                           # 0x80010014
    addiu   $sp, $sp, -8
    jr      $ra
    addiu   $sp, $sp, 8
    .data
stamps:                         # 0x80010020: two library stamps, libnum 1 and 3, version 0x47
    .byte 0x50, 0x73, 0x01, 0x00, 0x00, 0x00, 0x47, 0x00
    .byte 0x50, 0x73, 0x03, 0x00, 0x00, 0x00, 0x47, 0x00
