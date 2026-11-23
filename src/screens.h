/* screens.h - drawing whole screens from the converted art. */

#ifndef SCREENS_H
#define SCREENS_H

/* The show_ functions must only run while drawing is switched off: they
 * rewrite most of the graphics chip's memory. */

/* Load the overworld's terrain tiles and palettes, and the player's sprites
 * (hidden until place_player() puts them somewhere). The map itself is drawn
 * by scroll.c. */
void show_overworld(unsigned char player);

/* Put the player's top-left corner at (x, y) on screen, in pixels. Only
 * changes the sprite list in RAM, which the vblank handler copies to the
 * graphics chip, so it's safe to call at any time, every frame. */
void place_player(unsigned char x, unsigned char y);

/* The battle screen: an enemy standing on the backdrop, with empty text
 * boxes: a log of LOG_LINES lines across the top, and a one-line menu strip
 * at the bottom. Text goes in tile columns 1-30 of each (LOG_WIDTH). */
void show_battle(unsigned char enemy);

#define LOG_Y     2     /* the log's first line, in tile rows */
#define LOG_LINES 3
#define LOG_WIDTH 30
#define MENU_Y    27    /* the menu strip's line */

/* A page of the story: `text`, word-wrapped and double-spaced in one big
 * text box, with "PRESS A" at the bottom. The text goes in tile columns
 * STORY_X to STORY_X + STORY_WIDTH - 1, rows STORY_TOP to STORY_BOTTOM. */
void show_story(const char *text);

#define STORY_X      2
#define STORY_WIDTH  28
#define STORY_TOP    3
#define STORY_BOTTOM 24
#define STORY_PROMPT 26     /* "PRESS A" */

#endif
