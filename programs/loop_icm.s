; DMP3 (ICM-20948): a counted loop -- the vendor's `f9 da f4 <back>` idiom (bench/probe55.py).
; M[0x3f0] = the word to emit, M[0x3f4] = n; the body runs n+1 times per pass.
        .lineage icm
        .org    0x1000
        fmode   1               ; f1: leave mode 4 (state survives DMP_RST)
        fifo                    ; dd
        p0bank  3
        p0page  15              ; P0 -> 0x3f0
        p2bank  3
        p2page  14              ; P2 -> 0x3e0 (the counter)
        store                   ; dc
        mov     1               ; M[0x3e0] := n
loop:   fmode   1               ; every jump target starts with a width byte
        fifo
        mov     0               ; emit w0
        store
        dec                     ; f9: M[0x3e0] -= 1, F := result < 0
        if      nf              ; da
        jump    loop            ; while the count is not negative
        always                  ; d8: end the sticky predicate
        disable                 ; ff
