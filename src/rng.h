/* rng.h - random numbers. */

#ifndef RNG_H
#define RNG_H

/* Start the sequence from a seed. A seed of 0 is changed to 1 (see rng.c). */
void rng_seed(unsigned int seed);

/* 8 fresh random bits. */
unsigned char rng_byte(void);

/* A random number from 0 to n - 1, every value equally likely. n >= 1. */
unsigned char rng_below(unsigned char n);

#endif
