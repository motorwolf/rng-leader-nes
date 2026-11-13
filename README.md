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

Written in C with the [cc65](https://cc65.github.io/) toolchain.

Requirements: cc65 (tested with 2.18), make, and Python 3 for the local server.

```bash
brew install cc65     # macOS; on Debian/Ubuntu: apt install cc65
make                  # builds build/rng-leader.nes
make serve            # then open http://localhost:8000/play/
```

The ROM also runs in any NES emulator that supports mapper 1 (MMC1), such as
[Mesen](https://www.mesen.ca/).

The browser player (`play/`) uses [jsnes](https://github.com/bfirsh/jsnes). Controls:
arrow keys, Z = A, X = B, Enter = Start, Shift = Select.

## Layout

| Path | What it is |
|---|---|
| `src/header.s` | iNES header: tells emulators the cartridge type |
| `src/startup.s` | power-on setup and the vblank interrupt handler |
| `src/reset_stubs.s` | a small reset routine copied into every ROM bank |
| `src/mmc1.c` | MMC1 mapper: bank switching |
| `src/ppu.c` | sending tiles, maps and palettes to the graphics chip |
| `src/main.c` | the game |
| `mmc1.cfg` | linker config: where each piece goes in the 256 KB ROM |
