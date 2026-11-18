/* map.h - the overworld map. */

#ifndef MAP_H
#define MAP_H

/* The map's size in squares (32x32 pixels each), as in the original game. */
#define MAP_WIDTH  28
#define MAP_HEIGHT 16

/* What each square holds. The numbers match the order of the squares in
 * art/terrain.png, so they double as the art's square numbers. */
#define GRASS  0
#define SAND   1
#define CASTLE 2
#define FOREST 3

/* Where the castle is, and where the player starts. */
#define START_X 9
#define START_Y 1

/* The map itself, one byte per square, row by row: map[y][x]. */
extern unsigned char map[MAP_HEIGHT][MAP_WIDTH];

/* The desert square the item is hidden on (used in Milestone 6). */
extern unsigned char item_x, item_y;

/* Make a new random map. Seed the random numbers first (rng.h). */
void map_generate(void);

#endif
