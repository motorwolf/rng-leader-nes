/* battle.h - a fight. */

#ifndef BATTLE_H
#define BATTLE_H

/* Fight the given enemy (a battle art number, see art.h), on the battle
 * screen. Returns when the fight is over. Drawing the overworld again is up
 * to the caller. */
void battle(unsigned char enemy);

/* Add a message to the battle log: it scrolls the log up, wrapping onto
 * more lines if it's longer than one. Takes 3 frames per line, the log
 * being redrawn one line per vblank. */
void log_add(const char *text);

#endif
