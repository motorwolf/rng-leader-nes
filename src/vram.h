/* vram.h - the vblank queue: writing to the graphics chip while the screen
 * is on.
 *
 * The graphics chip's memory can only be written during vblank, which is
 * short, so writes are prepared during the frame as "runs" (an address, then
 * bytes) and the vblank handler (nmi in startup.s) copies them at the next
 * vblank. A batch is any number of runs, ended by vram_send(); one batch
 * goes out per vblank. */

#ifndef VRAM_H
#define VRAM_H

/* Start a run of `count` bytes at graphics address `addr`, written across a
 * row, or down a column if `down`. Then add the bytes with vram_add(). If
 * the last batch hasn't gone out yet, this waits for it first. A batch must
 * fit in 96 bytes: 3 per run, plus its bytes. */
void vram_run(unsigned int addr, unsigned char count, unsigned char down);
void vram_add(unsigned char value);

/* End the batch: the vblank handler writes it at the next vblank. While
 * paused, it's written right away instead. */
void vram_send(void);

/* Sleep until the next vblank: the heartbeat every NES game is built on. */
void wait_frame(void);

/* Stop the vblank handler touching the graphics chip, so C can write to it
 * directly (with drawing switched off): its writes would scramble C's. While
 * paused, it doesn't set the scroll either. A batch not yet written is
 * dropped, so pause only before redrawing the whole screen. */
void vram_pause(void);

/* Let the vblank handler write batches and set the scroll again. */
void vram_resume(void);

#endif
