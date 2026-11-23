/* game.c - the current game.
 *
 * The original picked a random regent and item for each new game
 * (begin_game in server.py). The item was one the player hadn't collected
 * yet, and Future Tech only once they'd collected everything else.
 *
 * For now (Milestone 5): the player is always HERO, and nothing is
 * collected yet (saving comes in Milestone 7), so the item is any but
 * Future Tech. */

#include <string.h>

#include "game.h"
#include "rng.h"

char player_name[NAME_SIZE];
unsigned char game_regent, game_item, game_killer;

void game_new(void) {
    strcpy(player_name, "HERO");
    game_regent = rng_below(REGENTS);

    /* One of the other ITEMS - 1: pick from that many, then step over
     * Future Tech's number. */
    game_item = rng_below(ITEMS - 1);
    if (game_item >= ITEM_FUTURE_TECH) {
        ++game_item;
    }
}
