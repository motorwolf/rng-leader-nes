/* vram.c - the vblank queue (see vram.h). The buffer and the code that
 * copies it are in startup.s; this fills it. */

#include "ppu.h"
#include "vram.h"

/* In startup.s. vram_ready is volatile: the vblank handler clears it. */
extern unsigned char ppu_updates_on;
extern unsigned char vram_buffer[96];
extern volatile unsigned char vram_ready;

/* Counts frames; startup.s adds one every vblank. "volatile" tells the
 * compiler it can change behind the code's back, so it must re-read it each
 * time instead of assuming it stays the same. */
extern volatile unsigned char frame_count;

/* How much of vram_buffer is filled. */
static unsigned char queued;

void vram_run(unsigned int addr, unsigned char count, unsigned char down) {
    /* A new batch: wait until the vblank handler has taken the last one, or
     * this would write over it. */
    if (queued == 0 && ppu_updates_on) {
        while (vram_ready) {
        }
    }
    vram_buffer[queued++] = down ? (count | 0x80) : count;
    vram_buffer[queued++] = addr >> 8;
    vram_buffer[queued++] = (unsigned char)addr;
}

void vram_add(unsigned char value) {
    vram_buffer[queued++] = value;
}

void vram_send(void) {
    unsigned char i, count, header;

    vram_buffer[queued] = 0;            /* the end */
    if (ppu_updates_on) {
        vram_ready = 1;                 /* last, so the handler never sees half a batch */
    } else {
        /* Paused (screen off): do what the handler would, right now. */
        i = 0;
        while ((header = vram_buffer[i]) != 0) {
            PPU_CTRL = (header & 0x80) ? (CTRL_SETTINGS | CTRL_DOWN) : CTRL_SETTINGS;
            ppu_set_addr((vram_buffer[i + 1] << 8) | vram_buffer[i + 2]);
            count = header & 0x7F;
            i += 3;
            while (count--) {
                PPU_DATA = vram_buffer[i++];
            }
        }
        PPU_CTRL = CTRL_SETTINGS;
    }
    queued = 0;
}

void wait_frame(void) {
    unsigned char start = frame_count;
    while (frame_count == start) {
        /* Nothing: just wait for the vblank handler to tick the counter. */
    }
}

void vram_pause(void) {
    ppu_updates_on = 0;
    vram_ready = 0;                     /* drop a batch not yet written */
}

void vram_resume(void) {
    ppu_updates_on = 1;
}
