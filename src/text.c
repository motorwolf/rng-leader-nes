/* text.c - drawing text with the font.
 *
 * The font is stored at 1 bit per pixel (see art.h): each character is 8
 * bytes, one per row, a 1 bit wherever the letter is. The graphics chip
 * wants 2 bits per pixel, in two "planes": 8 bytes of each pixel's low bit,
 * then 8 bytes of its high bit. So loading builds each tile on the way:
 * for a row r of the letter, and color c drawn wherever r has a 1,
 *
 *     plane 0 row = (c & 1) ? r : 0      plane 1 row = (c & 2) ? r : 0
 *
 * and the same with ~r (the bits flipped) for the space around the letter.
 * Storing 1 bit and expanding saves half the space, and lets the same font
 * be shown in any two colors. */

#include "art.h"
#include "mmc1.h"
#include "ppu.h"
#include "text.h"
#include "vram.h"

void text_load(unsigned char ink, unsigned char paper) {
    const unsigned char *glyph;
    unsigned char i, row;
    unsigned char plane[16];

    mmc1_set_bank(FONT_BANK);
    glyph = font.glyphs;
    ppu_set_addr(PPU_TILES + FONT_TILE * 16u);
    for (i = 0; i < font.count; ++i) {
        for (row = 0; row < 8; ++row) {
            plane[row]     = ((ink & 1) ? glyph[row] : 0) | ((paper & 1) ? ~glyph[row] : 0);
            plane[row + 8] = ((ink & 2) ? glyph[row] : 0) | ((paper & 2) ? ~glyph[row] : 0);
        }
        ppu_write(plane, 16);
        glyph += 8;
    }
}

void text_write(unsigned char x, unsigned char y, const char *text, unsigned char count) {
    vram_run(PPU_NAMETABLE0 + y * 32u + x, count, 0);
    while (count--) {
        /* The font starts at the space, character code 32. */
        vram_add(FONT_TILE + (unsigned char)(*text++ - ' '));
    }
    vram_send();
}

void text_print(unsigned char x, unsigned char y, const char *text) {
    unsigned char length = 0;
    while (text[length]) {
        ++length;
    }
    text_write(x, y, text, length);
}

unsigned char text_wrap(const char *text, unsigned char width) {
    unsigned char length = 0, cut;

    /* Count up to one past the width: if the text ends by then, it all fits. */
    while (text[length] && length <= width) {
        ++length;
    }
    if (length <= width) {
        return length;
    }

    /* Too long: break at the last space that keeps the line within the
     * width (text[width] being a space counts: the line then fills it
     * exactly), or mid-word if one word is longer than a whole line. */
    cut = width;
    while (cut && text[cut] != ' ') {
        --cut;
    }
    return cut ? cut : width;
}
