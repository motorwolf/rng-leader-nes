/* scroll.h - the scrolling camera over the overworld map. */

#ifndef SCROLL_H
#define SCROLL_H

/* The camera's top-left corner, in pixels from the map's top-left corner. */
extern unsigned int camera_x, camera_y;

/* Copy the terrain's tile and palette tables into RAM, so the streaming code
 * can read them without switching banks. Call after a new map is loaded. */
void scroll_load_terrain(void);

/* Point the scroll at the top-left of the first nametable, for screens that
 * don't scroll (the battle screen). The overworld's next scroll_draw_all()
 * points it back at the camera. */
void scroll_home(void);

/* Draw the whole screen at the camera. Only while the vblank queue is paused
 * (vram.h), with drawing off. */
void scroll_draw_all(void);

/* Move the camera to (x, y): along one axis at a time, at most 8 pixels.
 * Queues any newly needed column or row for the vblank handler. Call early
 * in a frame, right after a vblank, so it's done before the next one. */
void scroll_to(unsigned int x, unsigned int y);

#endif
