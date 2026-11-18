/* screens.h - drawing whole screens from the converted art. */

#ifndef SCREENS_H
#define SCREENS_H

/* Both must only run while drawing is switched off: they rewrite most of
 * the graphics chip's memory. */

/* A screen of the overworld map (map.h), with its top-left corner at map
 * square (cam_x, cam_y). Also loads the player's sprites, hidden until
 * place_player() puts them somewhere. */
void show_overworld(unsigned char player, unsigned char cam_x, unsigned char cam_y);

/* Put the player's top-left corner at (x, y) on screen, in pixels. Only
 * changes the sprite list in RAM, which the vblank handler copies to the
 * graphics chip, so it's safe to call at any time, every frame. */
void place_player(unsigned char x, unsigned char y);

/* The battle screen: an enemy standing on the backdrop. */
void show_battle(unsigned char enemy);

#endif
