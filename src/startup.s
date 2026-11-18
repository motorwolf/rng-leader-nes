; startup.s - the first code that runs at power-on, plus the vblank handler.
;
; This file has to be assembly: C can't run until this code has set up the
; things C relies on (a stack, cleared variables). It ends by calling main(),
; and from then on everything is C.
;
; Power-on, step by step:
;   1. Calm the hardware: screen, sound and interrupts off.
;   2. Wait for the graphics chip (the PPU) to warm up; it ignores us for
;      about two frames after power-on.
;   3. Clear RAM, which wakes up full of random leftovers.
;   4. Set up the C runtime and call main().
; The MMC1 is set up from C, at the start of main() (see mmc1.c).

.import _main, copydata, zerobss         ; main() and two C runtime helpers
.import __RAM_START__, __RAM_SIZE__      ; where RAM is, from mmc1.cfg
.importzp sp                             ; the C stack pointer

.export __STARTUP__ : absolute = 1       ; tells the C compiler startup code exists
.export reset, nmi, irq                  ; used by the reset stubs (reset_stubs.s)
.export _frame_count                     ; readable from C as frame_count
.export _ppu_updates_on, _scroll_ctrl, _scroll_x            ; the vblank queue,
.export _vram_column, _vram_column_addr, _vram_column_ready ; filled in by C:
.export _vram_attributes, _vram_attribute_addr, _vram_attributes_ready ; see nmi

; The graphics chip's registers: the addresses the processor writes to in
; order to talk to it.
PPUCTRL   = $2000
PPUMASK   = $2001
PPUSTATUS = $2002
PPUSCROLL = $2005
PPUADDR   = $2006
PPUDATA   = $2007
OAMADDR   = $2003
OAMDMA    = $4014

; ---------------------------------------------------------------------------
.segment "BSS"
_frame_count: .res 1    ; goes up by one every vblank: the game's clock

; The vblank queue (see nmi). C fills these in during the frame.
_ppu_updates_on:        .res 1   ; 0 while C is drawing with the screen off
_scroll_ctrl:           .res 1   ; the PPU_CTRL value, including which nametable is left
_scroll_x:              .res 1   ; the horizontal scroll within that nametable
_vram_column:           .res 30  ; a column of tiles, top to bottom
_vram_column_addr:      .res 2   ; where its top tile goes
_vram_column_ready:     .res 1   ; 1 = write it at the next vblank
_vram_attributes:       .res 8   ; a column of attribute (palette) bytes
_vram_attribute_addr:   .res 2   ; where the top one goes; the rest are 8 apart
_vram_attributes_ready: .res 1

.segment "OAM"
oam: .res 256           ; sprite list at $0200, sent to the graphics chip every frame

; ---------------------------------------------------------------------------
.segment "STARTUP"

reset:
    sei                 ; ignore interrupts while we set up
    cld                 ; the NES processor has no decimal mode; switch it off to be safe
    ldx #$40
    stx $4017           ; stop the sound chip's timer from interrupting us
    ldx #$FF
    txs                 ; set the processor's own stack to the top of $0100-$01FF
    inx                 ; X = 0
    stx PPUCTRL         ; no vblank interrupt yet
    stx PPUMASK         ; screen drawing off
    stx $4010           ; sample-playback interrupt off
    bit PPUSTATUS       ; reading this clears a stale "vblank happened" flag

@wait_vblank_1:         ; first of two waits for the graphics chip to warm up
    bit PPUSTATUS
    bpl @wait_vblank_1

    txa                 ; A = 0
@clear_ram:             ; zero all 2 KB of console RAM, 256 bytes per pass
    sta $0000,x
    sta $0100,x
    sta $0300,x
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    inx
    bne @clear_ram

    lda #$FF            ; sprites with a Y position of $FF are off-screen,
@hide_sprites:          ; so fill the sprite list with $FF to hide them all
    sta oam,x
    inx
    bne @hide_sprites

@wait_vblank_2:         ; second wait: the graphics chip is now ready
    bit PPUSTATUS
    bpl @wait_vblank_2

    ; The C stack starts at the top of RAM and grows downward.
    lda #<(__RAM_START__ + __RAM_SIZE__)
    sta sp
    lda #>(__RAM_START__ + __RAM_SIZE__)
    sta sp+1
    jsr zerobss         ; C variables that start at 0
    jsr copydata        ; C variables with a starting value: copy them from ROM

    jsr _main           ; hand over to C
@forever:
    jmp @forever        ; main() should never return, but just in case

; ---------------------------------------------------------------------------
; nmi: runs at the start of every vblank, once main() switches it on.
; It interrupts whatever the game is doing, so it saves and restores the
; registers it uses. Keep it short: vblank time is precious.
;
; Besides the sprite list, it copies the vblank queue: a column of tiles and
; a column of palette bytes that C prepared during the frame, then sets the
; scroll position. This part is in assembly because it's a race: the writes
; must finish before the picture starts drawing, about 2,270 cycles in. The
; same copy written in C took around 5,000. Here it's under 800.
;
; C fills the queue right after a vblank and sets the "ready" flags last, so
; this never sees a half-filled queue.
nmi:
    pha                 ; save A, X and Y
    txa
    pha
    tya
    pha

    lda #0
    sta OAMADDR
    lda #>oam
    sta OAMDMA          ; copy the 256-byte sprite list to the graphics chip

    lda _ppu_updates_on
    beq @done           ; C is drawing with the screen off: hands off

    ; A column of tiles. PPU_CTRL bit 2 makes each write move down a row.
    lda _vram_column_ready
    beq @attributes
    lda _scroll_ctrl
    ora #$04
    sta PPUCTRL
    bit PPUSTATUS       ; reset the address latch to "high byte next"
    lda _vram_column_addr+1
    sta PPUADDR
    lda _vram_column_addr
    sta PPUADDR
    ldx #0
@column:
    lda _vram_column,x
    sta PPUDATA
    inx
    cpx #30
    bne @column
    lda #0
    sta _vram_column_ready

    ; A column of palette bytes: 8 apart in memory, so one address each.
@attributes:
    lda _vram_attributes_ready
    beq @scroll
    lda _scroll_ctrl    ; back to moving right after each write
    sta PPUCTRL
    ldy _vram_attribute_addr   ; Y = the low byte of the address
    ldx #0
@attribute:
    lda _vram_attribute_addr+1
    sta PPUADDR
    sty PPUADDR
    lda _vram_attributes,x
    sta PPUDATA
    tya                 ; next address: 8 further on
    clc
    adc #8
    tay
    inx
    cpx #8
    bne @attribute
    lda #0
    sta _vram_attributes_ready

    ; The scroll position, last: the writes above disturb it.
@scroll:
    lda _scroll_ctrl
    sta PPUCTRL
    lda _scroll_x
    sta PPUSCROLL
    lda #0
    sta PPUSCROLL       ; vertical scroll: 0 for now

@done:
    inc _frame_count    ; tick
    pla                 ; restore Y, X and A
    tay
    pla
    tax
    pla
irq:                    ; no other interrupts are used, so they just return
    rti
