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

; The graphics chip's registers: the addresses the processor writes to in
; order to talk to it.
PPUCTRL   = $2000
PPUMASK   = $2001
PPUSTATUS = $2002
OAMADDR   = $2003
OAMDMA    = $4014

; ---------------------------------------------------------------------------
.segment "BSS"
_frame_count: .res 1    ; goes up by one every vblank: the game's clock

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
; register it uses. Keep it short: vblank time is precious.
nmi:
    pha                 ; save the A register
    lda #0
    sta OAMADDR
    lda #>oam
    sta OAMDMA          ; copy the 256-byte sprite list to the graphics chip
    inc _frame_count    ; tick
    pla                 ; restore A
irq:                    ; no other interrupts are used, so they just return
    rti
