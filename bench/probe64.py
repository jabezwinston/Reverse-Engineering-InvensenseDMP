#!/usr/bin/env python3
"""P6.20 -- does `fd n` shift the last ALU result?  And why probe58 C's loop never counted.

  A  fd after an ALU op, FIFO-routed:   00 fd 3f   (ADD, then arithmetic right by 1)
                                        0a fd 0f   (MUL, then left by 15 -- the vendor's product scale)
                                        21 fd 3f   (RSUB of known words)
     with P0 = 0x3f0 = [0x10000000, 0x20000000, -0x30000000, 0x04000000], P1 = 0x2f0 = [0x0c000000, ..]
     Each cell emits the op's own word and then the shift's word.  Also: does a MOV load the
     shifter (c0 fd 3f), does d4 override an ALU result (00 d4 fd 3f), does the shift
     compound after an ALU op (00 fd 3f fd 3f).
  B  the same RAM-routed (dc), reading M[P2] back.
  C  the skipped f4: `da f4 exit d8 ae f8` vs `da f4 exit d8 f1 ae f8` -- probe54 A showed a
     not-taken f4 enters mode 4; probe58 C's compare-at-top loop had its INC's page load
     right after such a jump.  If the page load became an I/O load, `d8 f1` fixes the loop.

    python3 probe64.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0
W = [0x10000000, 0x20000000, -0x30000000, 0x04000000]
V = [0x0C000000, 0x00000003, -0x08000000, 0x00000000]
SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf]


def sx(w): return w - (1 << 32) if w & 0x80000000 else w


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, b"".join(q32(x) for x in W))
    d.mem_write(0x2F0, b"".join(q32(x) for x in V))

    def run(prog, ms=5, n=6):
        for attempt in range(3):
            try:
                d.mem_write(0x1000, bytes([0xff]) * 64)
                d.mem_write(0x1F0, bytes(16))
                d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
                m = d.mem_read(0x1F0, 16)
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                return fc, us, d.words(raw), m
            except IOError:
                print("     (bridge error, re-initialising)"); time.sleep(0.5); d.prepare()
                d.mem_write(0x3F0, b"".join(q32(x) for x in W)); d.mem_write(0x2F0, b"".join(q32(x) for x in V))
        return 0, 0, [], bytes(16)

    def h(ws): return " ".join(f"{w:08x}" for w in ws)
    q30 = lambda v: (v & 0xFFFFFFFF)

    print("A. FIFO-routed: the op's word, then the shift's word(s)")
    print(f"   w0+v0 = {q30(W[0] + V[0]):08x}, >>1 = {q30((W[0] + V[0]) >> 1):08x};  w0*v0 (Q30) = {q30((W[0] * V[0]) >> 30):08x}, <<15 = {q30(((W[0] * V[0]) >> 30) << 15):08x}")
    for name, tail in (("00 fd 3f", [0x00, 0xfd, 0x3f]), ("00 fd 30 (>>16)", [0x00, 0xfd, 0x30]), ("00 fd 01 (<<1)", [0x00, 0xfd, 0x01]),
                       ("0a fd 0f", [0x0a, 0xfd, 0x0f]), ("21 fd 3f", [0x21, 0xfd, 0x3f]), ("00 fd 3f fd 3f", [0x00, 0xfd, 0x3f, 0xfd, 0x3f]),
                       ("c0 fd 3f", [0xc0, 0xfd, 0x3f]), ("00 d4 fd 3f", [0x00, 0xd4, 0xfd, 0x3f]), ("d4 00 fd 3f", [0xd4, 0x00, 0xfd, 0x3f]),
                       ("fd 3f (bare, after reset)", [0xfd, 0x3f]), ("00 d8 fd 3f", [0x00, 0xd8, 0xfd, 0x3f]), ("00 c2 fd 3f", [0x00, 0xc2, 0xfd, 0x3f])):
        fc, us, ws, m = run(SET + [0xdd] + tail + [0xff])
        print(f"  {name:28s} " + h(ws[:4]))

    print("B. RAM-routed into 0x1f0 (zeroed): 00 fd 3f / 0a fd 0f / 00 fd 4f (pre-advance)")
    for name, tail in (("dc 00 fd 3f", [0xdc, 0x00, 0xfd, 0x3f]), ("dc 0a fd 0f", [0xdc, 0x0a, 0xfd, 0x0f]), ("dc 00 fd 7f (adv)", [0xdc, 0x00, 0xfd, 0x7f]),
                       ("dc 00 d8 fd 3f", [0xdc, 0x00, 0xd8, 0xfd, 0x3f])):
        fc, us, ws, m = run(SET + tail + [0xff])
        print(f"  {name:28s} M[1f0..] " + " ".join(m[i:i+4].hex() for i in range(0, 16, 4)))

    print("C. the skipped f4 and the page load after it (count in M[0x3e0] seeded 0; F=1 so the da is not taken)")
    for name, mid in (("da f4 exit d8 ae f8", [0xd8, 0xae, 0xf8]), ("da f4 exit d8 f1 ae f8", [0xd8, 0xf1, 0xae, 0xf8]),
                      ("da f4 exit d8 bb ae f8", [0xd8, 0xbb, 0xae, 0xf8]), ("da f4 exit d8 f8 (no load)", [0xd8, 0xf8])):
        # 01 = RSUB B0 - A0 = 0x0c000000 - 0x10000000 < 0 -> F = 1 -> da not taken -> skip f4 exit -> d8 ..
        prog = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xbb, 0xae, 0xdc, 0x01] + [0xda, 0xf4, 0, 0] + mid + [0xff]
        exit_ = ENTRY + len(prog) - 1
        prog[11], prog[12] = exit_ >> 8, exit_ & 0xFF
        d.mem_write(0x3E0, bytes(16))
        d.mem_write(0x1000, bytes([0xff]) * 64); d.program(prog); d.fifo_reset(); d.T(1); d.wr(0, USER_CTRL, 0x40)
        m = d.mem_read(0x3E0, 8)
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        print(f"  {name:30s} M[3e0] = {m[:4].hex()}  M[3e4] = {m[4:].hex()}   (RSUB stored to 3e0 first; INC adds 1 if the page load was a RAM load)")


if __name__ == "__main__":
    main()
