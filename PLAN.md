# Plan

Each milestone ends with a ROM that runs, and is developed on its own branch and merged
through a pull request. The PR description records the problem, the constraint, the
options considered, the decision, and what went wrong.

## Milestones

| # | Milestone | Done when |
|---|---|---|
| 0 | **Foundation:** toolchain, MMC1 cartridge with battery-backed save RAM, build script, browser player | A blank ROM boots |
| 1 | **Art pipeline:** convert the original PNGs to NES tiles and palettes | Original and NES art shown side by side |
| 2 | **Overworld:** port the map generator from Python to C, scrolling camera, castle and desert | You can walk around a random map |
| 3 | **Randomness:** a random number generator, random encounters | Encounters trigger while walking |
| 4 | **Battles:** enemy drawn on the background layer, Attack/Run menu, integer-only formulas | A full fight plays out |
| 5 | **Text and data:** font, story templates, enemy and item tables generated from the original data files | The intro story appears on screen |
| 6 | **Game loop:** XP and levels, boss, item, return to the castle, win and death | The game can be played start to finish |
| 7 | **Persistence:** battery save, permadeath, graveyard and leaderboard | Progress survives a power-off |
| 8 | **Polish (optional):** title screen, sound, testing on real hardware | |
