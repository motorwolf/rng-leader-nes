/* screens.h - drawing whole screens from the converted art. */

#ifndef SCREENS_H
#define SCREENS_H

/* Both must only run while drawing is switched off: they rewrite most of
 * the graphics chip's memory. */

/* Load the overworld's terrain tiles and palettes, and the player's sprites
 * (hidden until place_player() puts them somewhere). The map itself is drawn
 * by scroll.c. */
void show_overworld(unsigned char player);

/* Put the player's top-left corner at (x, y) on screen, in pixels. Only
 * changes the sprite list in RAM, which the vblank handler copies to the
 * graphics chip, so it's safe to call at any time, every frame. */
void place_player(unsigned char x, unsigned char y);

/* The battle screen: an enemy standing on the backdrop. */
void show_battle(unsigned char enemy);

#endif
