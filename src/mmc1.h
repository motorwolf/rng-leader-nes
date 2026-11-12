/* mmc1.h - talking to the MMC1 mapper chip on the cartridge. */

#ifndef MMC1_H
#define MMC1_H

/* Put the MMC1 into the layout the game expects: bank 15 fixed at $C000,
 * switchable banks at $8000, save RAM switched on. Call once, first thing. */
void mmc1_init(void);

/* Choose which bank (0-14) appears in the switchable half at $8000.
 * Must only be called from code in the fixed bank. */
void mmc1_set_bank(unsigned char bank);

#endif
