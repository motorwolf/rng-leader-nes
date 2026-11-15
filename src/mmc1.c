/* mmc1.c - talking to the MMC1 mapper chip on the cartridge.
 *
 * The MMC1 is told what to do by writing to cartridge ROM addresses. ROM can't
 * be changed, so the ROM ignores those writes, but the MMC1 listens to them.
 *
 * Its quirk: it only has a one-bit input. To set one of its settings (a
 * register), you write five times, sending one bit of the value each time,
 * lowest bit first. On the fifth write it combines the five bits and applies
 * them. A serial input like this needed fewer pins, which made the chip cheaper
 * in 1987, at the cost of every setting change taking five writes.
 *
 * The MMC1 has four registers. Which one the five bits go to depends on the
 * address of the fifth write:
 *   $8000-$9FFF  control: banking mode and screen mirroring
 *   $A000-$BFFF  graphics bank 0 \  only matter with graphics ROM; with
 *   $C000-$DFFF  graphics bank 1 /  graphics RAM we just set them to 0
 *   $E000-$FFFF  program bank: which bank shows at $8000, plus a save-RAM switch
 */

#include "mmc1.h"

#define MMC1_CONTROL   0x8000
#define MMC1_GFX_BANK0 0xA000
#define MMC1_GFX_BANK1 0xC000
#define MMC1_PRG_BANK  0xE000

/* Send a 5-bit value to one MMC1 register, one bit per write. */
static void mmc1_write(unsigned int reg, unsigned char value) {
    unsigned char i;
    for (i = 0; i < 5; ++i) {
        /* Only the lowest bit of each write counts; the MMC1 ignores the rest. */
        *(volatile unsigned char *)reg = value;
        /* Shift right by one: the next bit moves into the lowest position. */
        value >>= 1;
    }
    /* Caution for later: if the vblank handler ever switches banks too, it
     * could interrupt these five writes halfway and scramble both. For now
     * only main-line code calls this, so that can't happen. */
}

void mmc1_init(void) {
    /* Control register, 5 bits:
     *   bits 0-1  screen mirroring: 2 = vertical. (This decides how the
     *             background wraps when scrolling; revisited in Milestone 2.)
     *   bits 2-3  program banking mode: 3 = "bank 15 fixed at $C000, $8000
     *             switchable", the layout from mmc1.cfg
     *   bit  4    graphics banking mode: 0 = one 8 KB unit (fine for graphics RAM)
     * Together: 0 1 1 1 0 in binary = 0x0E. */
    mmc1_write(MMC1_CONTROL, 0x0E);

    mmc1_write(MMC1_GFX_BANK0, 0);
    mmc1_write(MMC1_GFX_BANK1, 0);

    mmc1_set_bank(0);
}

void mmc1_set_bank(unsigned char bank) {
    /* Program bank register: bits 0-3 pick the bank (0-14). Bit 4 = 0 keeps
     * the save RAM switched on. Later we'll use bit 4 to lock the save RAM
     * except while saving, to protect it from power-off glitches. */
    mmc1_write(MMC1_PRG_BANK, bank & 0x0F);
}
