/* screens.h - drawing whole screens from the converted art. */

#ifndef SCREENS_H
#define SCREENS_H

/* Both must only run while drawing is switched off: they rewrite most of
 * the graphics chip's memory. */

/* A screen of the overworld map (map.h), with its top-left corner at map
 * square (cam_x, cam_y), and the player on the castle if it's in view. */
void show_overworld(unsigned char player, unsigned char cam_x, unsigned char cam_y);

/* The battle screen: an enemy standing on the backdrop. */
void show_battle(unsigned char enemy);

#endif
