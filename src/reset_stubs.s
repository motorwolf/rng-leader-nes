; reset_stubs.s - a tiny power-on safety net at the end of every bank.
;
; The problem: on real hardware the MMC1 doesn't promise what state it wakes up
; in, so at power-on any bank might be showing at $C000-$FFFF instead of the
; fixed bank 15. The processor's first act is to read the startup address from
; $FFFC, at the very end of whichever bank that is. If that bank had no valid
; address there, the game wouldn't boot.
;
; The fix: every bank ends with the same 16 bytes:
;   - a 10-byte stub that resets the MMC1 and jumps to the real startup code
;   - the three vectors (startup addresses), all pointing at that stub
;
; The trick that makes it work: the stub sits at the same position in every
; bank. When the stub tells the MMC1 to reset, bank 15 instantly appears at
; $C000, right under the code that's running. Bank 15 has an identical stub in
; the identical spot, so the processor carries on without noticing the swap.
;
; Emulators always start the MMC1 in the normal state, so this only matters on
; a real console. Some original MMC1 games occasionally failed to boot without it.

.import reset, nmi, irq   ; defined in startup.s, in the fixed bank

; Where the stub sits when its bank is showing at $C000-$FFFF, which is the
; only time the processor reads it. (In the ROM file, switchable banks are built
; for $8000, so their copy is placed at $BFF0, which is $FFF0 minus $4000.)
STUB_ADDR = $FFF0

; One macro that writes the stub, used once per bank below.
.macro RESET_STUB segname
    .segment segname
    sei                 ; ignore interrupts
    ldx #$FF
    txs                 ; reset the processor's stack
    stx $8000           ; any value with the top bit set resets the MMC1, which
                        ; puts bank 15 at $C000 (the "fixed last bank" mode)
    jmp reset           ; now safely in bank 15: run the real startup code
    .word nmi, STUB_ADDR, irq   ; the vectors: vblank handler, power-on, other interrupts
.endmacro

RESET_STUB "STUB00"
RESET_STUB "STUB01"
RESET_STUB "STUB02"
RESET_STUB "STUB03"
RESET_STUB "STUB04"
RESET_STUB "STUB05"
RESET_STUB "STUB06"
RESET_STUB "STUB07"
RESET_STUB "STUB08"
RESET_STUB "STUB09"
RESET_STUB "STUB10"
RESET_STUB "STUB11"
RESET_STUB "STUB12"
RESET_STUB "STUB13"
RESET_STUB "STUB14"
RESET_STUB "STUB15"     ; the fixed bank gets one too, so all 16 banks match
