/* rng.c - random numbers from a linear-feedback shift register (LFSR).
 *
 * The NES has no random number source, so games compute "pseudo-random"
 * numbers: a sequence that looks random but is fully decided by its starting
 * value, the seed. Same seed, same sequence (useful for testing, and how
 * speedrunners manipulate luck).
 *
 * This is a 16-bit Galois LFSR. Each step shifts the state right by one; if
 * the bit that fell off was 1, the state is XORed with a fixed mask. With the
 * right mask, the state visits every value from 1 to 65535 once before
 * repeating (a "maximal-length" sequence). 0xB400 is one such mask: it marks
 * bits 16, 14, 13 and 11 as the "taps", from published tables of masks that
 * work. Zero is the one state it can never leave (shifting and XORing nothing
 * gives nothing), so it must never be the seed.
 *
 * Cost: a shift, a test and sometimes an XOR per step. No multiply or divide,
 * which the 6502 doesn't have. */

#include "rng.h"

static unsigned int state = 1;

void rng_seed(unsigned int seed) {
    state = seed ? seed : 1;
}

/* One step of the generator: one fresh bit. */
static void step(void) {
    unsigned char low_bit = state & 1;
    state >>= 1;
    if (low_bit) {
        state ^= 0xB400;
    }
}

unsigned char rng_byte(void) {
    unsigned char i;
    /* Each step makes one new bit, so 8 steps give a byte that shares no bits
     * with the previous one. */
    for (i = 0; i < 8; ++i) {
        step();
    }
    return (unsigned char)state;
}

unsigned char rng_below(unsigned char n) {
    unsigned char mask = 0;
    unsigned char r;

    /* The smallest all-ones mask that covers n - 1: for n = 5 (0-4), 4 is
     * binary 100, so the mask is 111 (7). */
    while (mask < (unsigned char)(n - 1)) {
        mask = (mask << 1) | 1;
    }

    /* Rejection sampling: take that many random bits; if the result is too
     * big, throw it away and try again. Every value 0..n-1 stays equally
     * likely, unlike the usual "random % n", which also needs a slow division
     * here. The mask is under twice n, so at least half the tries succeed. */
    do {
        r = rng_byte() & mask;
    } while (r >= n);
    return r;
}
