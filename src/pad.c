/* pad.c - reading the controller.
 *
 * The NES controller is a shift register: a chip holding 8 bits, one per
 * button, that it hands over one at a time. Writing 1 then 0 to $4016
 * "latches" it (takes a snapshot of the buttons); then each read of $4016
 * gives the next button in the lowest bit, in a fixed order: A, B, Select,
 * Start, Up, Down, Left, Right. Same idea as reading a serial port. */

#include "pad.h"

#define JOYPAD1 (*(volatile unsigned char *)0x4016)

unsigned char pad_read(void) {
    unsigned char i;
    unsigned char buttons = 0;

    JOYPAD1 = 1;    /* take the snapshot... */
    JOYPAD1 = 0;    /* ...and start shifting it out */
    for (i = 0; i < 8; ++i) {
        /* Make room on the right, then add this button's bit. After 8 reads
         * A has been shifted up to the top bit (0x80), Right is in bit 0. */
        buttons = (buttons << 1) | (JOYPAD1 & 1);
    }
    return buttons;
}
