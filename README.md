# RNG_LEADER for the NES

A port of [RNG_LEADER](https://github.com/motorwolf/RNG_LEADER), a browser RPG I built
in 2019 (Python/Flask backend, vanilla JavaScript frontend, my own pixel art), to the
Nintendo Entertainment System.

The original had a random overworld, Final Fantasy–style random battles, an item hunt
with a boss, permadeath, and a graveyard and leaderboard stored in a database. This
version rebuilds all of that to run on a 1985 console with 2 KB of RAM, no operating
system, no database and no network.

**Status:** in progress. See [PLAN.md](PLAN.md).

## Why

To learn how games were made under real hardware limits, and how the decisions of a
modern web app (a database, floating-point maths, `Math.random()`, a server) translate to
a machine that has none of those things.

## Building

Written in C with the [cc65](https://cc65.github.io/) toolchain. Build instructions
will be added in Milestone 0.
