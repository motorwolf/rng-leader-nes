/* screens.h - drawing whole screens from the converted art. */

#ifndef SCREENS_H
#define SCREENS_H

/* Both must only run while drawing is switched off: they rewrite most of
 * the graphics chip's memory. */

/* The overworld terrain, with a player standing in the middle. */
void show_overworld(unsigned char player);

/* The battle screen: an enemy standing on the backdrop. */
void show_battle(unsigned char enemy);

#endif
