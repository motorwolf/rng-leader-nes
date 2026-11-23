/* game.h - the current game: who's playing, and what this game picked. */

#ifndef GAME_H
#define GAME_H

#include "data.h"

/* The player's name, in capitals. */
extern char player_name[NAME_SIZE];

/* This game's regent and the item they want back (numbers into regents[]
 * and items[], data.h), and the enemy that killed the player, if one has
 * (into enemies[]). */
extern unsigned char game_regent, game_item, game_killer;

/* Start a new game: pick a regent and an item. */
void game_new(void);

#endif
