/* scroll.h - the scrolling camera over the overworld map. */

#ifndef SCROLL_H
#define SCROLL_H

/* The camera's left edge, in pixels from the map's left edge. */
extern unsigned int camera_x;

/* Copy the terrain's tile and palette tables into RAM, so the streaming code
 * can read them without switching banks. Call after a new map is loaded. */
void scroll_load_terrain(void);

/* Stop the vblank handler from touching the graphics chip, so C can write to
 * it directly (with drawing switched off). Its writes would scramble C's. */
void scroll_pause(void);

/* Let the vblank handler write the queue and set the scroll again. */
void scroll_resume(void);

/* Draw the whole screen at camera_x. Only while paused, with drawing off. */
void scroll_draw_all(void);

/* Move the camera to x (at most 8 pixels from where it is). Queues any
 * newly needed column for the vblank handler. Call early in a frame, right
 * after a vblank, so it's done before the next one. */
void scroll_to(unsigned int x);

#endif
