/* ppu.c - the mailbox for sending data to the graphics chip.
 *
 * The processor can't reach the PPU's memory directly; it's on a separate
 * address system. Instead it uses two PPU registers as a mailbox:
 *   PPU_ADDR  set the address, in two writes (high byte, then low byte)
 *   PPU_DATA  each write stores one byte there; the address then moves on by one
 */

#include "ppu.h"

void ppu_set_addr(unsigned int addr) {
    /* PPU_ADDR and PPU_SCROLL share a hidden switch that tracks "first or
     * second byte?". Reading PPU_STATUS resets it to "first", so the two
     * writes below are guaranteed to land as high byte, then low byte. */
    (void)PPU_STATUS;
    PPU_ADDR = (unsigned char)(addr >> 8);   /* high byte: shift the top 8 bits down */
    PPU_ADDR = (unsigned char)addr;          /* low byte: casting keeps only the bottom 8 bits */
}

void ppu_write(const unsigned char *data, unsigned int count) {
    while (count--) {
        PPU_DATA = *data++;   /* send the byte data points at, then move to the next one */
    }
}

void ppu_fill(unsigned char value, unsigned int count) {
    while (count--) {
        PPU_DATA = value;
    }
}
