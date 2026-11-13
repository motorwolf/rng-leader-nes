/* ppu.h - talking to the graphics chip (the PPU, "picture processing unit"). */

#ifndef PPU_H
#define PPU_H

/* The PPU's registers: addresses the processor writes to in order to talk to
 * the graphics chip. "volatile" because every read and write has an effect. */
#define PPU_CTRL   (*(volatile unsigned char *)0x2000)  /* vblank interrupt, which map to show */
#define PPU_MASK   (*(volatile unsigned char *)0x2001)  /* drawing on/off for background and sprites */
#define PPU_STATUS (*(volatile unsigned char *)0x2002)  /* reading it resets the address latch */
#define PPU_SCROLL (*(volatile unsigned char *)0x2005)  /* scroll position: X, then Y */
#define PPU_ADDR   (*(volatile unsigned char *)0x2006)  /* the mailbox address: high byte, then low */
#define PPU_DATA   (*(volatile unsigned char *)0x2007)  /* the mailbox data: one byte per write */

/* Where things live in the PPU's own address space. */
#define PPU_TILES      0x0000   /* tile pictures: our 8 KB of graphics RAM */
#define PPU_NAMETABLE0 0x2000   /* the first screen-sized map of tile numbers */
#define PPU_ATTRIBUTES 0x23C0   /* palette choices for that map, per 16x16 pixel block */
#define PPU_PALETTES   0x3F00   /* 8 palettes of 4 colours: 4 for background, 4 for sprites */

/* Everything below must only run while drawing is switched off, or inside
 * vblank. Otherwise it disturbs the PPU mid-frame and the picture glitches. */

/* Point the mailbox at a PPU address. */
void ppu_set_addr(unsigned int addr);

/* Send count bytes from data to the mailbox, starting where it points. */
void ppu_write(const unsigned char *data, unsigned int count);

/* Send the same byte count times. */
void ppu_fill(unsigned char value, unsigned int count);

#endif
