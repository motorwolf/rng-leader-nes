/* story.h - telling the story: filling in its templates. */

#ifndef STORY_H
#define STORY_H

#include "data.h"

/* The last story block filled in, with a 0 at the end. */
extern char story[STORY_SIZE];

/* Fill in a story block (STORY_START and so on, data.h) with this game's
 * values (game.h), into story[]. */
void story_format(unsigned char block);

/* Fill in a story block and show it on its own screen until the player
 * presses A. Drawing whatever comes next is up to the caller. */
void story_tell(unsigned char block);

#endif
