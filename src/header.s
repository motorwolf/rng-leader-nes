; header.s - the iNES header: a 16-byte label at the front of the ROM file.
;
; Real NES cartridges have no header. The console simply runs whatever chips
; are wired to it, and the cartridge's circuit board *is* its description.
; A ROM file is just the chip contents dumped to disk, so emulators need to be
; told what board those chips came from. The iNES format (from an emulator of
; the same name, 1996) does that with these 16 bytes, and it became the standard.
;
; Our board: Nintendo's MMC1 mapper, 256 KB of program ROM, 8 KB of graphics
; RAM (no graphics ROM), and 8 KB of battery-backed save RAM. This matches a
; real board Nintendo manufactured, called SNROM, used by Zelda and Final Fantasy.

.segment "HEADER"

    .byte "NES", $1A    ; magic number: "NES" followed by an MS-DOS end-of-file
                        ; character, so printing the file to a 1990s DOS screen
                        ; would stop after "NES" instead of dumping garbage.

    .byte 16            ; program ROM size, in 16 KB slices: 16 x 16 KB = 256 KB
    .byte 0             ; graphics ROM size, in 8 KB units: 0 means "none, the
                        ; board has graphics RAM instead", which the game fills
                        ; with whatever tiles the current scene needs

    ; Flags 6, bit by bit (each bit is one on/off switch):
    ;   bit 0: screen mirroring - ignored here, the MMC1 sets it from code
    ;   bit 1: 1 = the board has battery-backed save RAM at $6000-$7FFF
    ;   bits 4-7: the lower half of the mapper number. MMC1 is mapper 1.
    .byte %00010010     ; mapper 1 (in the top four bits) + battery (bit 1)

    .byte %00000000     ; flags 7: upper half of the mapper number (0), nothing else

    .byte 0             ; save RAM size in 8 KB units: 0 means the standard 8 KB
    .res 7, 0           ; the remaining bytes are unused; pad with zeros
