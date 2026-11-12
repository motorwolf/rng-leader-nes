# Makefile - builds the ROM. Run `make` to build, `make clean` to start fresh.
#
# make reads this file as a list of rules:
#
#     target: prerequisites
#     <TAB>command
#
# "To produce target, you need prerequisites. If any prerequisite is newer
# than the target (or the target doesn't exist yet), run the command."
# make compares file timestamps, so it only rebuilds what actually changed.
# (The indent before each command must be a real tab character, not spaces.)
#
# The pipeline for this project:
#
#   src/main.c ──cc65──► build/main.s ──ca65──► build/main.o ─┐
#   src/mmc1.c ──cc65──► build/mmc1.s ──ca65──► build/mmc1.o ─┤
#   src/startup.s ─────────────ca65──► build/startup.o ───────┼─ld65─► build/rng-leader.nes
#   src/reset_stubs.s ─────────ca65──► build/reset_stubs.o ───┤   (laid out by mmc1.cfg)
#   src/header.s ──────────────ca65──► build/header.o ────────┘
#
# cc65 compiles C into 6502 assembly, ca65 assembles that into machine code
# (object files, .o), and ld65 links the objects into the final ROM.

# --- Settings -------------------------------------------------------------

NAME  := rng-leader
BUILD := build
ROM   := $(BUILD)/$(NAME).nes

# The source files. Adding a new .c or .s file to src/ means adding its name here.
C_SOURCES   := main mmc1
ASM_SOURCES := header startup reset_stubs

# Every source file becomes one object file in build/.
OBJECTS := $(addprefix $(BUILD)/, $(addsuffix .o, $(ASM_SOURCES) $(C_SOURCES)))

# cc65 options:
#   -t nes  target the NES (selects the right runtime library and settings)
#   -O      optimise the generated code
#   -i      prefer inlining small things over calling them (faster, slightly bigger)
#   -r      keep frequently used local variables in fast zero-page "registers"
#   -s      inline some standard library calls (strlen, memcpy and similar)
CFLAGS := -t nes -Oirs

# --- Rules ----------------------------------------------------------------

# The first rule is the default: plain `make` builds the ROM.
all: $(ROM)

# Link: combine every object file into the ROM, using mmc1.cfg as the map.
# nes.lib is cc65's runtime library: helper routines the compiled C calls
# for things the 6502 can't do in one instruction, like multiplying.
# -m also writes a map file: a report of where everything landed and how much
# space each bank has left. Worth a look as the game grows.
#   $@ = this rule's target (the ROM)
$(ROM): $(OBJECTS) mmc1.cfg
	ld65 -C mmc1.cfg -m $(BUILD)/$(NAME).map -o $@ $(OBJECTS) nes.lib

# Compile: C to assembly. "%" is a wildcard, so this one rule covers every .c file.
#   $< = the first prerequisite (the .c file)
# The "| $(BUILD)" part means "the build folder must exist first", without
# rebuilding everything whenever the folder's timestamp changes.
$(BUILD)/%.s: src/%.c | $(BUILD)
	cc65 $(CFLAGS) $< -o $@

# Assemble: compiler output (in build/) to machine code.
$(BUILD)/%.o: $(BUILD)/%.s
	ca65 -t nes $< -o $@

# Assemble: hand-written assembly (in src/) to machine code.
$(BUILD)/%.o: src/%.s | $(BUILD)
	ca65 -t nes $< -o $@

# Header dependencies: these C files #include mmc1.h, so if the header (the
# "menu") changes, they must be recompiled even though their own .c is unchanged.
$(BUILD)/main.s $(BUILD)/mmc1.s: src/mmc1.h

$(BUILD):
	mkdir -p $(BUILD)

# Delete everything make produced.
clean:
	rm -rf $(BUILD)

# Build, then serve the project folder so the browser player can load the ROM.
# Open http://localhost:8000/play/ and press Ctrl+C here to stop.
serve: all
	@echo "Open http://localhost:8000/play/  (Ctrl+C to stop)"
	python3 -m http.server 8000

# "all", "clean" and "serve" are names of jobs, not files, so tell make not to
# look for files with those names.
.PHONY: all clean serve

# Keep the intermediate build/*.s files instead of auto-deleting them, so you
# can read the assembly the compiler generated from your C.
.SECONDARY:
