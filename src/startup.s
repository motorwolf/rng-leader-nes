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
.export _ppu_updates_on, _scroll_ctrl, _scroll_x, _scroll_y ; the vblank queue,
.export _vram_buffer, _vram_ready                            ; filled in by C: see nmi

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
_ppu_updates_on: .res 1   ; 0 while C is drawing with the screen off
_scroll_ctrl:    .res 1   ; the PPU_CTRL value, including which nametable is left
_scroll_x:       .res 1   ; the horizontal scroll within that nametable
_scroll_y:       .res 1   ; the vertical scroll, 0-239
_vram_buffer:    .res 96  ; runs of bytes to write (format at nmi)
_vram_ready:     .res 1   ; 1 = write the buffer at the next vblank

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
; Besides the sprite list, it copies the vblank queue that C prepared during
; the frame (new tiles and palette bytes for the scrolling camera), then sets
; the scroll position. This part is in assembly because it's a race: the
; writes must finish before the picture starts drawing, about 2,270 cycles
; in. The same copy written in C took around 5,000.
;
; The queue is a list of runs, each:
;   1 byte   how many bytes follow (1-127); bit 7 set = write down a column
;            (each byte goes 32 further on) instead of across a row
;   2 bytes  the graphics-memory address of the first one, high byte first
;   n bytes  the bytes
; and a 0 at the end. C fills it right after a vblank and sets _vram_ready
; last, so this never sees a half-filled queue.
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

    lda _vram_ready
    beq @scroll
    bit PPUSTATUS       ; reset the address latch to "high byte next"
    ldx #0              ; X = position in the queue
@run:
    lda _vram_buffer,x  ; the run's length byte
    beq @runs_done      ; 0: the end
    inx
    tay                 ; Y = the length byte, for now
    lda _scroll_ctrl
    cpy #$80            ; bit 7 set (128 or more)?
    bcc @across
    ora #$04            ; PPU_CTRL bit 2: each write moves down a row
@across:
    sta PPUCTRL
    lda _vram_buffer,x  ; the address, high byte...
    sta PPUADDR
    inx
    lda _vram_buffer,x  ; ...then low byte
    sta PPUADDR
    inx
    tya
    and #$7F            ; drop bit 7: Y = how many bytes
    tay
@byte:
    lda _vram_buffer,x
    sta PPUDATA
    inx
    dey
    bne @byte
    beq @run            ; Y is 0 here, so this always branches
@runs_done:
    lda #0
    sta _vram_ready

    ; The scroll position, last: the writes above disturb it.
@scroll:
    lda _scroll_ctrl
    sta PPUCTRL
    lda _scroll_x
    sta PPUSCROLL
    lda _scroll_y
    sta PPUSCROLL

@done:
    inc _frame_count    ; tick
    pla                 ; restore Y, X and A
    tay
    pla
    tax
    pla
irq:                    ; no other interrupts are used, so they just return
    rti
