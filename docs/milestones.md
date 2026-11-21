# Milestones

The write-up for each finished milestone, as it appeared in its pull request: the problem, the constraints, the options considered, the decision, and what went wrong. (See PLAN.md for the full list.)

The pull request numbers in the merge commits for Milestones 0–2 refer to an earlier copy of this repository.

## Milestone 0: Foundation

Milestone 0: a cartridge that boots, a build, and a way to play it in the browser.

The ROM boots on an MMC1 board, copies placeholder tiles into graphics RAM, and draws a grass-and-trees field. No game yet; this is the ground everything else stands on.

### Problem

The original game assumed a server, a database, a filesystem and a browser. The NES has 2 KB of RAM, a 32 KB window for the cartridge, and nothing else. Before porting anything, the project needs a cartridge layout with room to grow, a way to save, and a one-command build.

### Decisions

**Mapper: MMC1, laid out like Nintendo's SNROM board** (Zelda, Final Fantasy).
- *Constraint:* the CPU can only see 32 KB of cartridge at a time, and the game needs to save.
- *Options:* NROM (no mapper, 32 KB total, no saving), UxROM (bank switching, no save RAM), MMC1 (bank switching and battery-backed save RAM).
- *Decision:* MMC1. It's the only common mapper that gives both, and it's well supported by emulators.

**Program ROM: 256 KB, the largest MMC1 supports.**
- Avoids running out of space mid-project. The cost is nothing in an emulator, and it can shrink later.
- Banks 0–14 swap in at $8000; bank 15 is fixed at $C000 and holds the startup code, the C runtime and anything that must always be reachable.

**Graphics RAM instead of graphics ROM.**
- *Options:* ROM (tiles fixed at build time, swapped in by bank) or RAM (the game copies in whatever tiles the current scene needs).
- *Decision:* RAM, the more flexible option. The art pipeline in Milestone 1 can produce any tile set per scene without fitting a fixed bank layout.

**8 KB of battery-backed save RAM at $6000.**
- Replaces the original's database for the graveyard and leaderboard (Milestone 7).

**Startup in assembly, everything else in C (cc65).**
- Power-on setup and the vblank interrupt need exact control and are written once. All game logic is C.

**A reset stub in every bank.**
- The MMC1's bank after power-on isn't defined, so any bank could be sitting at $C000. Every bank ends with the same 16 bytes: reset the mapper and jump to the real startup code.

**A browser player (jsnes) for quick checks.**
- `make serve` builds the ROM and serves `play/`. Fast to iterate; real testing happens in Mesen and eventually on hardware.

### What went wrong

- **Keys didn't work on a Dvorak layout.** The player mapped keys by `e.code` (physical position). Switched to `e.key`. Quick taps that landed between frames were also being dropped; key presses are now latched until the next frame reads them.
- **`ld65` rejected the multi-bank layout** until each bank in the linker config had a `bank` attribute.
- **The trees lined up in diagonal stripes.** Simple arithmetic on x and y makes patterns. Replaced it with a hash that scatters properly.
- **The field takes about 0.7 s to draw.** The hash multiplies three times per square, and the 6502 has no multiply instruction, so that's 2,880 software multiplications. Fine for a placeholder; the real generator (Milestone 3) will use a shift-and-XOR random number generator instead.

### Not verified

- **The reset stubs under a random power-on state.** jsnes always powers on the same way. To check in Mesen, which can randomise it.


## Milestone 1: Art pipeline

### Problem

The original game's art is web PNGs: enlarged by odd factors (2×, 7×, 20×, and about 11.97× with blurring), full RGB, any number of colors per image. The NES takes 8×8 tiles at 2 bits per pixel, colors from a fixed set of 64, and strict palette rules.

### Constraints

- Sprites: 4 palettes of 3 colors plus transparent, chosen per 8×8 tile.
- Backgrounds: 4 palettes of 3 colors plus one color shared by the whole screen, chosen per 16×16 area.
- 64 sprites, at most 8 per scanline.
- 256 background tiles in graphics RAM.
- ROM comes in 16 KB banks, and only the fixed bank is always readable.

### Pipeline (`tools/convert.py`, run by `make`)

1. **Shrink to true size.** The scale is the GCD of color run lengths. For the blurred player sheet, a grid search that samples block centers.
2. **Map to NES colors.** The color-difference method is chosen per image by eye: OKLab (a perceptual color space) for terrain and players, weighted RGB for the backdrop and enemies.
3. **Reduce colors.** Greedy merging within each tile or area, then k-means palette packing with 30 seeded random restarts.
4. **Encode, deduplicate, emit C.** The arrays are placed across the switchable banks, with a small index in the fixed bank.

### Decisions

- **Strict 1:1 with the original art.** The one exception: grass, sand and forest are cut to a repeating 16×16 piece, so terrain takes 28 tiles instead of 64. An 8×8 piece was tried and showed a visible grid.
- **The battle screen is one background picture:** the backdrop at 4× with the enemy at 4×, matching the original's proportions (backdrop stretched to fill the window, enemy about three-quarters of its height). Options considered:
  - **Enemy as sprites, with black outlines on the background layer.** Keeps more colors, but the 64-sprite limit caps the enemy at 64×64, which is too small.
  - **Enemy at 4× on the background layer (chosen).** At that scale a tile covers 2×2 art pixels and a palette area covers 4×4, so tiles repeat heavily (28–61 new tiles per enemy) and few colors are lost.
- **The enemy stands on the ground**, as in the original. This also keeps it clear of the sun's palette.

### What went wrong

- Greedy palette packing dropped small details (lips, tongues). Fixed with k-means refinement and restarts.
- OKLab matched the near-black outline color to dark teal. Fixed with a lightness cutoff.
- OKLab turned the backdrop hills hot pink. Fixed by choosing the method per image.
- The first battle layout left enemies floating in the sky.
- The art outgrew the fixed bank and moved to the switchable banks.

### Result

An art viewer: the overworld terrain with a player, and the battle screen for each enemy. Start switches screens; Left/Right changes the player or enemy.


## Milestone 2: Overworld

### Problem

Milestone 2: a random overworld to walk around. The original generated a 28×16 map of 32×32 squares (896×512 pixels) and showed it in a browser window. The NES screen is 256×240, and its background layer holds only two screens of tiles at once.

### Constraints

- The graphics chip can only be written during vblank, about 2,270 CPU cycles per frame.
- Two nametables (32×30 tiles each), set side by side: a buffer 64 tiles wide and 30 tall that wraps in both directions.
- Palettes are chosen per 16×16 area, packed four to an attribute byte covering 32×32.
- No hardware random number generator, and no clock to seed one.

### Map generation (`src/map.c`, `src/rng.c`)

- **RNG:** a 16-bit Galois LFSR (mask $B400, period 65,535), seeded from a frame counter at the first Start press. `rng_below(n)` uses rejection sampling, so results aren't biased toward low numbers.
- **Trees:** a tree chance of 10, 20 or 30% is picked once per map, then applied to each square. The original meant to do this, but a bug made every square 50/50.
- **Desert:** a random blob instead of the original's rectangle, with the same range of sizes (3–7 × 1–3 squares), grown from the same spot by Eden growth: repeatedly turn a random neighbor of a random desert square to sand. The item is hidden on one of its squares.
- **Castle:** at the start position, as in the original.

### Walking (`src/main.c`)

- One square per step, 16 frames per step. Holding a direction keeps walking.
- The camera keeps the player 96 pixels from the top-left corner and stops at the map's edges.

### Scrolling (`src/scroll.c`, `src/startup.s`)

- **Streaming:** map tile (column c, row t) lives in buffer column c mod 64 and row t mod 30. When the camera crosses a tile boundary, the column or row about to come into view overwrites one that just left.
- **Vblank queue:** C prepares each frame's writes as runs (address, length, across or down) in a 96-byte buffer, and the vblank handler, in assembly, copies them. A full column plus its palette bytes, or a full row plus its palette bytes, finishes by scanline 14, inside vblank.
- **Pausing the queue:** during a full redraw (new map, drawing switched off), the vblank handler skips the queue, so its writes can't scramble the ones C makes directly.
- **Palettes across the wrap:** 30 rows isn't a multiple of 4, so once the buffer wraps, one attribute byte's top and bottom halves can hold different map squares. Each byte is built from whichever map rows are in its two halves right now. 30 is a multiple of 2, so each 16×16 half always lies within one square.

### What went wrong

- **Left edge:** the player could walk off the left edge. Integer promotion made a bounds check signed, and a negative result passed it. Fixed with an `unsigned char` cast; a compiler warning ("comparison is constant") pointed at it.
- **Copy too slow:** the first version copied columns to the graphics chip from C and overran vblank, finishing at scanlines 48–63. Moving the copy into the assembly vblank handler fixed it.
- **Palette band:** the first vertical version wrote palette bytes as soon as a new row arrived. For half of each two-row palette area the old row was still on screen, so a strip about 8 pixels tall, just inside the edge, took the wrong colors. Palettes are now written only once both rows of their area are new.
- **Colors:** the forest read as water, and the grass specks looked rough. Forest is now $0A and grass $1A.
- **Name clash:** the header guard `MAP_H` collided with a map-height constant. The constants are now `MAP_WIDTH` and `MAP_HEIGHT`.

### Known limits

- **Edge rows:** while scrolling vertically, the outermost 8 pixels at the top or bottom can show wrong tiles or colors for a frame. When the camera sits between tile rows, 31 rows are visible in a 30-row buffer. CRT overscan hid this band, and many NES games have the same artifact.
- **New map:** the screen goes blank for about 50 frames, half generating the map and half redrawing it. A Start or direction tap during that time can be missed.

### Result

A random overworld: the D-pad walks the player across a 28×16 map, the camera follows in all four directions, and Start makes a new map.

