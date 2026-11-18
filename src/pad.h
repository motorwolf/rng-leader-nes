/* pad.h - reading the controller. */

#ifndef PAD_H
#define PAD_H

/* One bit per button, in the order the controller sends them. */
#define PAD_A      0x80
#define PAD_B      0x40
#define PAD_SELECT 0x20
#define PAD_START  0x10
#define PAD_UP     0x08
#define PAD_DOWN   0x04
#define PAD_LEFT   0x02
#define PAD_RIGHT  0x01

/* The buttons held down on controller 1 right now. */
unsigned char pad_read(void);

#endif
