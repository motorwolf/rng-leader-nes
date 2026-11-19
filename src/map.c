/* map.c - generating the overworld, ported from create_map() in the
 * original game (game.py).
 *
 * The original:
 *   - every square is grass or trees;
 *   - a rectangular desert, 3-7 squares wide and 1-3 tall, sits centered
 *     near the bottom, with the item hidden on one of its squares;
 *   - the castle is at the start position.
 *
 * Changed in the port:
 *   - Trees: the original picked a tree percentage of 10-30%, but a bug made
 *     every square a 50/50 choice. This does what it meant to.
 *   - The desert is a blob instead of a rectangle, with the same range of
 *     sizes, grown from the same spot. */

#include "map.h"
#include "rng.h"

unsigned char map[MAP_HEIGHT][MAP_WIDTH];
unsigned char item_x, item_y;

/* Tree chances out of 256 (rng_byte() gives 0-255): about 10%, 20%, 30%. */
static const unsigned char tree_chance[3] = { 26, 51, 77 };

/* The four neighbors of a square, as steps in x and y: right, left, down, up. */
static const signed char step_x[4] = { 1, -1, 0, 0 };
static const signed char step_y[4] = { 0, 0, 1, -1 };

/* The desert's squares so far, so growth can pick a random one. The biggest
 * desert is 7 x 3 = 21 squares. */
#define DESERT_MAX 21
static unsigned char desert_x[DESERT_MAX];
static unsigned char desert_y[DESERT_MAX];

/* Where the desert starts growing: the middle of the original's bottom
 * desert row, one row above the map's edge. */
#define DESERT_START_X (MAP_WIDTH / 2)
#define DESERT_START_Y (MAP_HEIGHT - 2)

/* The desert stays out of the bottom row, as in the original, and well away
 * from the castle at the top. */
#define DESERT_TOP    4
#define DESERT_BOTTOM (MAP_HEIGHT - 2)

static void grow_desert(void) {
    unsigned char size, count, i, dir, x, y;

    /* The same sizes the original's rectangle could have: width x height. */
    size = (3 + rng_below(5)) * (1 + rng_below(3));

    map[DESERT_START_Y][DESERT_START_X] = SAND;
    desert_x[0] = DESERT_START_X;
    desert_y[0] = DESERT_START_Y;
    count = 1;

    /* Eden growth: pick a random desert square, then a random neighbor of it,
     * and turn that neighbor to sand. Repeat until big enough. Growing only
     * from squares already in the blob keeps it in one piece, and picking at
     * random makes the edge lumpy. */
    while (count < size) {
        i = rng_below(count);
        dir = rng_byte() & 3;               /* 0-3: one of the 4 neighbors */
        x = desert_x[i] + step_x[dir];
        y = desert_y[i] + step_y[dir];
        /* x is unsigned, so stepping left from 0 wraps around to 255, which
         * the x < MAP_WIDTH test also catches. */
        if (x < MAP_WIDTH && y >= DESERT_TOP && y <= DESERT_BOTTOM && map[y][x] != SAND) {
            map[y][x] = SAND;
            desert_x[count] = x;
            desert_y[count] = y;
            ++count;
        }
    }

    /* Hide the item on one of the desert squares. */
    i = rng_below(count);
    item_x = desert_x[i];
    item_y = desert_y[i];
}

void map_generate(void) {
    unsigned char x, y, chance;

    chance = tree_chance[rng_below(3)];
    for (y = 0; y < MAP_HEIGHT; ++y) {
        for (x = 0; x < MAP_WIDTH; ++x) {
            map[y][x] = (rng_byte() < chance) ? FOREST : GRASS;
        }
    }

    grow_desert();
    map[START_Y][START_X] = CASTLE;
}
