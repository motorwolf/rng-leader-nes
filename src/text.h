/* text.h - drawing text with the font. */

#ifndef TEXT_H
#define TEXT_H

/* Load the font into the background tiles (after the screen's own), with
 * its letters in color `ink` and the space around them in color `paper`.
 * Colors are palette slots, 0-3: 0 is the screen's shared color, 1-3 are
 * the three colors of whichever palette the text's 16x16 area uses. Only
 * while drawing is switched off: it writes 1,520 bytes. */
void text_load(unsigned char ink, unsigned char paper);

/* Write `text` on the first nametable, starting at tile column x, row y.
 * Only while drawing is switched off, for now. */
void text_print(unsigned char x, unsigned char y, const char *text);

#endif
