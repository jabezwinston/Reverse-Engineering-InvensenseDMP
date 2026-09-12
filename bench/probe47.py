#!/usr/bin/env python3
"""P6.4 -- pointer addressing on DMP3: bc/bd/be and the f4 mode, with address-encoded memory.

Instrument: every 4-byte word of the 16 KB holds its own address (word at A = A), except the
program at 0x1000.  Any read then tells us where the pointer resolved.  The vendor image is
overwritten; reload with icm.ICM.load() (probe43) afterwards.

  A. P0: MOV to FIFO after pointer loads.        prog = <loads> dd f1 c0 ff
  B. P1: A-zero add:  P0 -> word 0 (= 0), so the sum is M[P1].  prog = b0 80 <loads> dd f1 00 ff
  C. P2: RAM-routed MOV of a marker, then scan memory for the marker.

    python3 probe47.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

SIZE = 0x4000
MARK = 0xDEAD0000


def fill_aem(d):
    for a in range(0, SIZE, 64):
        d.mem_write(a, b"".join(q32(x) for x in range(a, a + 64, 4)))


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    print("filling address-encoded memory ...")
    fill_aem(d)
    back = d.mem_read(0x3F0, 8)
    print("  check M[0x3f0] =", back.hex(), "(expect 000003f0 000003f4)")

    def emit(name, prog, ms=8):
        d.program(prog)
        d.fifo_reset(); n, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 24))
        ws = d.words(raw)
        print(f"  {name:24s} {bytes(prog).hex():24s} -> " + " ".join(f"{w:08x}" for w in ws[:5]))
        return ws

    print("A. P0 (MOV c0 -> FIFO)")
    T = [0xdd, 0xf1, 0xc0, 0xff]
    emit("b3 8f",            [0xb3, 0x8f] + T)
    emit("b2 85",            [0xb2, 0x85] + T)
    emit("bc b3 8f",         [0xbc, 0xb3, 0x8f] + T)
    emit("bc bc b3 8f",      [0xbc, 0xbc, 0xb3, 0x8f] + T)
    emit("bc bc bc b3 8f",   [0xbc, 0xbc, 0xbc, 0xb3, 0x8f] + T)
    emit("bc x4 b3 8f",      [0xbc, 0xbc, 0xbc, 0xbc, 0xb3, 0x8f] + T)
    emit("b3 8f bc",         [0xb3, 0x8f, 0xbc] + T)
    emit("b3 bc 8f",         [0xb3, 0xbc, 0x8f] + T)
    emit("bd b3 8f",         [0xbd, 0xb3, 0x8f] + T)
    emit("be b3 8f",         [0xbe, 0xb3, 0x8f] + T)
    print("   f4 mode:")
    emit("f4d8 b3 8f",       [0xf4, 0xd8, 0xb3, 0x8f] + T)
    emit("f4d8 b3 80",       [0xf4, 0xd8, 0xb3, 0x80] + T)
    emit("f4d8 b3 81",       [0xf4, 0xd8, 0xb3, 0x81] + T)
    emit("f4d8 b0 8f",       [0xf4, 0xd8, 0xb0, 0x8f] + T)
    emit("f4d8 b3 8f f1 c0", [0xf4, 0xd8, 0xb3, 0x8f, 0xf1] + T)
    emit("b3 8f f4d8 8f",    [0xb3, 0x8f, 0xf4, 0xd8, 0x8f] + T)
    emit("f4d8 b3 8f; f1 8f",[0xf4, 0xd8, 0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0x8f, 0xc0, 0xff])
    emit("f4d8 bc b3 8f",    [0xf4, 0xd8, 0xbc, 0xb3, 0x8f] + T)
    emit("f4d8 b3 8f bc",    [0xf4, 0xd8, 0xb3, 0x8f, 0xbc] + T)

    print("B. P1 (P0 -> 0, add -> FIFO)")
    T1 = [0xdd, 0xf1, 0x00, 0xff]
    emit("b7 9f",            [0xb0, 0x80, 0xb7, 0x9f] + T1)
    emit("bd b7 9f",         [0xb0, 0x80, 0xbd, 0xb7, 0x9f] + T1)
    emit("bd bd b7 9f",      [0xb0, 0x80, 0xbd, 0xbd, 0xb7, 0x9f] + T1)
    emit("bc b7 9f",         [0xb0, 0x80, 0xbc, 0xb7, 0x9f] + T1)
    emit("f4d8 b7 9f",       [0xb0, 0x80, 0xf4, 0xd8, 0xb7, 0x9f] + T1)

    print("C. P2 (RAM-routed MOV of a marker at 0x3f0, then scan)")
    def store(name, loads):
        d.mem_write(0x3F0, q32(MARK))
        d.program([0xb3, 0x8f] + loads + [0xdc, 0xf1, 0xc0, 0xff])
        d.T(5); d.wr(0, USER_CTRL, 0x40)
        mem = d.mem_read(0, SIZE)
        hits = [a for a in range(0, SIZE, 4) if int.from_bytes(mem[a:a+4], "big") == MARK and a != 0x3F0]
        print(f"  {name:24s} -> stored at {[hex(a) for a in hits]}")
        for a in hits: d.mem_write(a, q32(a))          # repair the instrument
    store("bb ae",            [0xbb, 0xae])
    store("be bb ae",         [0xbe, 0xbb, 0xae])
    store("be be bb ae",      [0xbe, 0xbe, 0xbb, 0xae])
    store("f4d8 bb ae",       [0xf4, 0xd8, 0xbb, 0xae])
    store("f4d8 bb ae f1",    [0xf4, 0xd8, 0xbb, 0xae, 0xf1])


if __name__ == "__main__":
    main()
