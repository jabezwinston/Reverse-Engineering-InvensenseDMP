#!/usr/bin/env python3
"""P4.x -- the MPU-6050 re-measures queued by the DMP3 sessions (UNKNOWNS.md section 7).

Custom programs at PRGM_START (0x300, Finding 23) over the stock 1929 image's data; data
pages 0x70 (P0 = W), 0x60 (P1 = V), 0x240 (P2, RAM-routed destination); FIFO-routed cells
read the FIFO head after a short `T`.  The stock image is restored at the end.

  A  fd:   bare `fd 08` over a seeded RAM word / `d4 fd 08` / `00 fd 3f` (shift of the sum?) /
           `fd 08 08` (does fd suppress the next store, as probe31 said)
  B  predicate scope: `08 d1 d9 c4 c6 d8 c0` with Z = 0 -- single-shot skips c4 only, sticky
           skips c4 and c6
  C  the flag without d1: `<op> d9 c6` / `da c6` over zero, positive and negative results,
           INC / DEC of a seeded word; then the DMP3 rule "F frozen under an armed predicate"
  D  c8..cf: RAM-routed c8 / cc under f1 f2 f3 over a seeded destination
  E  fc:   `fc c0 21 c4 c6` -- a one-byte swap prefix (4 words) or DMP3's three bytes (2 words)

    python3 probe67.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
W = [5, -20, 7, 0]
V = [-5, 2, -9, 30]
RATE = 1000.0


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")
def sx(w): return w - (1 << 32) if w & 0x80000000 else w


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = dmpinit.dmp_init(b)
    b.wr(SMPLRT_DIV, 0)                                   # 1 kHz
    b.mem_write(0x70, b"".join(q32(x) for x in W))
    b.mem_write(0x60, b"".join(q32(x) for x in V))
    SET = [0xf1, 0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4]     # P0 -> 0x70, P1 -> 0x60, P2 -> 0x240

    def run(prog, ms=30, n=6, seed=None):
        prog = bytes(prog + [0xff] * 4)
        b.mem_write(0x70, b"".join(q32(x) for x in W)); b.mem_write(0x60, b"".join(q32(x) for x in V))   # re-seed: the first run showed 0x70 clobbered
        if seed is not None: b.mem_write(0x240, q32(seed) * 4)
        b.mem_write(PRGM, prog)
        b.wr(USER_CTRL, 0x00)
        nn, us = b.cmd(f"T {ms}").split()
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 4 * n))
        m = b.mem_read(0x240, 16)
        b.wr(USER_CTRL, 0x00)
        p0 = b.mem_read(0x70, 16); p1 = b.mem_read(0x60, 16)
        if p0 != b"".join(q32(x) for x in W) or p1 != b"".join(q32(x) for x in V):
            print(f"     !! data pages changed: 0x70 = {p0.hex()}  0x60 = {p1.hex()}")
        ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]
        return fc / (int(us) / 1e6 * RATE), ws, m

    def show(name, prog, note="", seed=None, n=6):
        bpp, ws, m = run(prog, seed=seed, n=n)
        print(f"  {name:30s} {bytes(prog).hex():28s} {bpp:6.2f} B/pass  " + " ".join(f"{sx(w):+d}" if abs(sx(w)) < 100000 else f"{w:08x}" for w in ws)
              + (f"   M[240..] " + " ".join(m[i:i+4].hex() for i in range(0, 16, 4)) if seed is not None else "") + (f"   | {note}" if note else ""))

    print("B. predicate scope (Z = 0 from `08 d1`: 7 != 0).  MOVs: c4 -> +7, c6 -> 0, c0 -> +5")
    show("08 d1 d9 c4 c6 d8 c0", SET + [0xdd, 0x08, 0xd1, 0xd9, 0xc4, 0xc6, 0xd8, 0xc0], "single-shot: +7 0 +5 ; sticky: +7 +5")
    show("00 d1 d9 c4 c6 d8 c0 (Z=1)", SET + [0xdd, 0x00, 0xd1, 0xd9, 0xc4, 0xc6, 0xd8, 0xc0], "0 +7 0 +5 either way")
    show("08 d1 da c4 c6 d8 c0", SET + [0xdd, 0x08, 0xd1, 0xda, 0xc4, 0xc6, 0xd8, 0xc0], "")
    show("08 d1 d9 f1 c4 c6 d8 c0", SET + [0xdd, 0x08, 0xd1, 0xd9, 0xf1, 0xc4, 0xc6, 0xd8, 0xc0], "mode byte transparent?")

    print("C. the flag without d1:  <op> <pred> c6 ; c6 emits 0 (P0 word 3).  ops: 00 -> 0, 08 -> +7, 20 -> -25, 01 -> -10, 21 -> +15")
    print("     op        d9  da   (DMP3: d9 = result < 0)")
    for name, op in (("00 (=0)", [0x00]), ("08 (+7)", [0x08]), ("20 (-25)", [0x20]), ("01 (-10)", [0x01]), ("21 (+15)", [0x21]),
                     ("00 d1 (=0)", [0x00, 0xd1]), ("08 d1", [0x08, 0xd1]), ("(none)", [])):
        res = []
        for pred in (0xd9, 0xda):
            bpp, ws, m = run(SET + [0xdd] + op + [pred, 0xc6, 0xd8], n=3)
            emitted = [sx(w) for w in ws]
            res.append("T" if (len(emitted) >= 2 and emitted[1] == 0) or (not op and emitted and emitted[0] == 0) else "-")
        print(f"     {name:12s} {res[0]}   {res[1]}")
    print("   INC / DEC of M[0x240] (RAM-routed), then dd <pred> c6:")
    for name, op, seed in (("f8 on 1", [0xf8], 1), ("f8 on -1", [0xf8], 0xFFFFFFFF), ("f9 on 1", [0xf9], 1), ("f9 on 0", [0xf9], 0), ("f9 on -1", [0xf9], 0xFFFFFFFF)):
        res = []
        for pred in (0xd9, 0xda):
            bpp, ws, m = run(SET + [0xdc] + op + [0xdd, pred, 0xc6, 0xd8], seed=seed, n=2)
            res.append("T" if ws and sx(ws[0]) == 0 else "-")
        print(f"     {name:12s} {res[0]}   {res[1]}   M[240] = {m[:4].hex()}")
    print("   F frozen under an armed predicate?  01 (F=1) d9 08 c6 -> c6 emitted iff frozen")
    show("01 d9 08 c6", SET + [0xdd, 0x01, 0xd9, 0x08, 0xc6, 0xd8], "-10 +7 0 if frozen; -10 +7 if 08 cleared F")
    show("08 da 01 c6", SET + [0xdd, 0x08, 0xda, 0x01, 0xc6, 0xd8], "")

    print("D. c8..cf, RAM-routed into 0x240 (seed c0ffee00); P0 word 0 = 0x01234567 for this section")
    b.mem_write(0x70, q32(0x01234567) + q32(0x89ABCDEF) + q32(0x0BADF00D) + q32(0xDEADBEEF))
    for op in (0xc0, 0xc8, 0xcc):
        for fx in (0xf1, 0xf2, 0xf3):
            bpp, ws, m = run(SET + [0xdc, fx, op], seed=0xC0FFEE00, n=1)
            print(f"  {op:02x} under {fx:02x}: M[240] = {m[:4].hex()}")
    b.mem_write(0x70, b"".join(q32(x) for x in W))

    print("E. fc: one-byte swap prefix (MPU, probe35) or three bytes (DMP3)?  fc c0 21 c4 c6: prefix -> 4 words, 3-byte -> +7 0")
    show("fc c0 21 c4 c6", SET + [0xdd, 0xfc, 0xc0, 0x21, 0xc4, 0xc6], "")
    show("fc 21 c4 c6", SET + [0xdd, 0xfc, 0x21, 0xc4, 0xc6], "swapped RSUB: P0w0 - P1w1 = 5 - 2 = +3 ; unswapped +15")
    show("21 c4 c6 (control)", SET + [0xdd, 0x21, 0xc4, 0xc6], "+15 +7 0")

    print("A. fd on the MPU")
    show("dc fd 08 (bare, RAM)", SET + [0xdc, 0xfd, 0x08], "seed stays = no store; 0 = stores zero; shifted = shifter", seed=0xC0FFEE00)
    show("dc d4 fd 08", SET + [0xdc, 0xd4, 0xfd, 0x08], "0x500 (= 5 << 8) if the MPU has the shifter", seed=0xC0FFEE00)
    show("dc 00 fd 3f", SET + [0xdc, 0x00, 0xfd, 0x3f], "5 + -5 = 0 .. use 08: ", seed=0xC0FFEE00)
    show("dc 08 fd 3f", SET + [0xdc, 0x08, 0xfd, 0x3f], "M[240] = 7 (ADD) then 3 (>>1) if fd shifts the sum; 7 if fd is NOSTORE", seed=0xC0FFEE00)
    show("dc fd 08 08", SET + [0xdc, 0xfd, 0x08, 0x08], "probe31: fd suppresses the next store -> seed stays; DMP3: fd stores, 08 stores 7", seed=0xC0FFEE00)
    show("dd 08 fd 3f (FIFO)", SET + [0xdd, 0x08, 0xfd, 0x3f], "+7 then +3 if the shifter; +7 alone if NOSTORE")
    show("dd fd 08 08 (FIFO)", SET + [0xdd, 0xfd, 0x08, 0x08], "")

    print("   what did d4 / fd do to the pages?  (the pages are re-seeded before every cell; a '!!' line above shows a change)")
    show("dc d4", SET + [0xdc, 0xd4], "", seed=0xC0FFEE00)
    show("dc d4 08", SET + [0xdc, 0xd4, 0x08], "", seed=0xC0FFEE00)
    show("dd d4 c0 c2", SET + [0xdd, 0xd4, 0xc0, 0xc2], "does d4 move a pointer")
    show("dc d5", SET + [0xdc, 0xd5], "", seed=0xC0FFEE00)
    show("dc d2", SET + [0xdc, 0xd2], "", seed=0xC0FFEE00)
    show("dc 0a d2", SET + [0xdc, 0x0a, 0xd2], "MUL then d2: the product's low word on DMP3", seed=0xC0FFEE00)
    show("dd e0", SET + [0xdd, 0xe0, 0xc0], "e0 on the MPU: RET on DMP3")
    show("dd e2 c0", SET + [0xdd, 0xe2, 0xc0], "e2: INT on DMP3")
    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
