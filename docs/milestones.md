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


## Milestone 3: Encounters

### Problem

Milestone 3: random fights while walking the overworld. The random number generator this milestone called for already landed in Milestone 2, for map generation, so what's left is encounters.

### The original

`movePlayer` in `static/js/game.js`:

- After every step, `Math.floor(Math.random() * 100) <= 10` starts a fight: 11%, probably meant as 10%. Terrain doesn't matter.
- It works out an enemy level (the player's, ±1), then ignores it and asks the server for a level 1 enemy.
- Stepping on the item's square starts the boss fight, and the random roll still runs on the same step, so two fights can start at once.
- The castle square heals the player, and a fight can start on the same step.

### Decisions

- **Chance:** 26 in 256 (about 10%), checked when a step finishes.
- **No roll on the castle or item squares.** The castle will heal and the item square will have the boss (both Milestone 6), and a random fight on top of either is a bug.
- **The Squash Bug is back.** In `data/enemies` it was level 10 and every other regular enemy level 1, so it never appeared. Levels were never finished, so the pool is all 14 regular enemies. The battle art is in the original's enemy order, so number 0 is the boss and is left out.
- **Placeholder fight:** the battle screen until A is pressed, then back to the overworld at the same spot. The fight itself is Milestone 4.

### Changes

- `src/main.c`: the roll, the enemy pick, and `fight()`, which swaps to the battle screen and back.
- `src/scroll.c`: `scroll_home()` points the scroll at the first nametable's corner for the battle screen, which doesn't scroll. The vblank handler sets the scroll from these values every frame, so without it the battle screen would be drawn offset to wherever the overworld camera was.
- `Makefile`: `main.c` now includes `art.h`, for the enemy count.
- `README.md`: the `main.c` row lists the new controls.

### Testing

In the emulator, about 570 random steps: 40 fights, all 14 enemies seen, and in 10 fights checked, the player and camera returned exactly where they were.

### Known limits

- **Slow return:** entering a fight blanks the screen for about 12 frames, but returning takes about 47, because the whole overworld is redrawn. Worth revisiting in Milestone 4.
- **Top row:** on the map's top row the player's top 8 pixels don't show. A sprite can't start on the screen's first scanline, so those sprites land off the bottom. This is in the overscan band and is left as is.

### Result

Walking the overworld triggers random fights with any of the 14 regular enemies; A returns to the map.


## Milestone 4: Battles

### Problem

Milestone 4: the fight itself. The original's battle was a web page: the enemy picture, a scrolling message box, and Attack and Run buttons. The NES battle screen from Milestone 1 is one full-screen background picture, with no font, no free tiles and no free palette.

### Constraints

- **Palettes:** every enemy uses all 4 background palettes.
- **Tiles:** 256 background tiles, and the enemies take up to 153 of them.
- **Writing while drawing:** the graphics chip can only be written during vblank, and messages have to appear while the screen is on.
- **Message length:** the original's messages are up to about 40 characters, and the screen is 32 tiles wide.

### Decisions

**Font: Press Start 2P (OFL), stored at 1 bit per pixel.**
- 95 characters (ASCII 32–126) at tiles 161–255.
- The loader expands each character to 2 bits per pixel, in whichever two palette colors are asked for. That halves the space and lets one font be drawn in any colors.

**Text colors: the backdrop's palette.**
- *Options:* free a palette by merging two of an enemy's palettes (loses colors from the 1:1 art), draw the text as sprites (8 per scanline, too few), or reuse an existing palette.
- *Decision:* palette 0, the backdrop's, which is the same for every enemy: pink ink on purple, with an orange border. `convert.py` checks that every row under a text box uses palette 0 for every enemy.

**Layout: a 3-line log across the top, and a 1-line menu strip at the bottom.**
- *Options:* a single 2-line box at the bottom (covers less of the enemy, but long messages don't fit), or a taller log panel.
- *Decision:* the log at the top, kept short enough to sit in the sky above the enemy. Lines wrap at word boundaries, and the newest is at the bottom, like the original's box. The strip shows Attack, Run Away and the player's HP.
- Box borders take 8 tiles at 153–160, so the enemy art must fit in 153 tiles. `convert.py` checks this.

**The vblank queue moves into `vram.c`.**
- Scrolling and text both need it now. Starting a new batch waits for the previous one to be sent, so callers can queue one line after another.

**Combat: the original's math, in whole numbers, with four bugs fixed.**
- **To hit:** a miss is 3 in (dex + 20).
- **Damage:** a roll from base to 3 × base − 1, where base = weapon + strength / 2, minus the target's armor.
- **Turn order:** higher dex goes first, and a tie goes to the player. One turn in 10 the order swaps.
- **Run:** a 30% chance, or 10% against a faster enemy. A failed run gives the enemy a free hit.
- **Fixes:**
  - a hit could do 0 damage; now it does at least 1;
  - a fighter at exactly 0 HP kept fighting; now 0 is dead;
  - dying when the enemy struck first showed two death messages;
  - misses showed the name in normal case and hits in capitals.

**Placeholders until later milestones:**
- The player is always the Elephant.
- Enemy stats are typed in from `data/enemies`.
- HP carries over between fights, and dying refills it.
- Data tables are Milestone 5; experience, the castle's healing and real death are Milestones 6 and 7.

### What went wrong

- **No room for text:** the first mockup put the log in a 2-line box at the bottom, and most messages didn't fit.
- **Writing text with the screen on:** the queue lived in `scroll.c` and was tied to the camera. Moving it into its own file came before any text could be drawn mid-fight.

### Testing

In the emulator, 218 fights played automatically:

| | Expected | Measured |
|---|---|---|
| Player miss rate | 14.3% | 15.1% (39 of 259) |
| Enemy miss rate | 14.3% | 14.7% (43 of 293) |
| Player damage | 6–19 | 6–19 |
| Regular enemy damage | 1–6 | 1–6 |
| Sadwich damage | 7–24 | 9–24 |
| Run success | 30% | 25% (51 of 202) |

The run rate is about 1.5 standard deviations low, within chance. After a death, the next fight starts at 20/20.

### Known limits

- **Difficulty:** the Sadwich hits for 7–24 against the Elephant's 20 HP, as in the original, which never got the levels that would have balanced it. Revisit with experience in Milestone 6.
- **Message pace:** each message pauses 20 frames, and each log line takes 3 frames to redraw.

### Result

Random fights play out: Left/Right picks Attack or Run, A chooses, the log tells the fight, and winning, running or dying returns to the map.
