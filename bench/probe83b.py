#!/usr/bin/env python3
"""P7.4b -- follow-ups to probe83.

  A  `fc cX Y` as an immediate compare: F = (field  <cond>  T), field = P1 word (X&3) & 0x3f,
     T = Y >> 2, cond = Y & 3 (0 EQ, 1 GT, 2 LT, 3 NE).  All 64 field values, with junk above
     bit 5, against eight T values and all four conditions: 64 x 32 predictions.
     Patterns live at 0x400 + 16 i (P1 block 1 via `bd`), clear of the sensor words at 0x0.
  B  where a store goes after `bf`: `bf ba a5` + RAM-routed MOV of 0x000000c3; host banks 0-3
     and all 16 KB of RAM compared before/after, and the FIFO count.
  C  `fc X Y` with X < 0xc0, as the vendor writes it (`fc 51 00 10`, `fc 3d 00`, `fc 80 04`):
     is X an operand (3-byte form) or an ALU op after a 1-byte `fc`?  P0 = 0x3f0 [5 3 0 0],
     P1 = 0x3e0 [7 11 13 17], P2 = 0x3d0 (RAM-routed, zeroed); the page after the run and F.

    python3 probe83b.py /dev/ttyUSB1
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

M0, M1 = 0x600D600D, 0x5E9A5E9A
SIDE = {(0, 0x19), (0, 0x1A), (0, 0x1B), (0, 0x72), (0, 0x7D), (0, 0x70), (0, 0x71)}
VOLATILE = {(0, r) for r in range(0x2D, 0x3B)} | {(0, 0x7C), (0, 0x7E), (0, 0x17), (0, 0x1C), (0, 0x03), (0, 0x68)}


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()

    def run(prog, ms=5, nbytes=512):
        d.program(prog); d.fifo_reset(); d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = b""
        while len(raw) < min(fc, nbytes):
            raw += d.fifo_read(min(128, min(fc, nbytes) - len(raw)))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return fc, d.words(raw)

    print("A. fc c0 Y over all 64 fields (junk above bit 5)")
    pats = [v | ((v * 0x9E3779B1 + 0x5A5A0000) & 0xFFFFFFC0) for v in range(64)]
    for i, p in enumerate(pats):
        d.mem_write(0x400 + 16 * i, q32(p) + bytes(12))
    d.mem_write(0x3F0, q32(M0) + q32(M1) + bytes(8))
    cond = {0: lambda f, t: f == t, 1: lambda f, t: f > t, 2: lambda f, t: f < t, 3: lambda f, t: f != t}
    name = "EQ GT LT NE".split()
    bad = total = 0
    for T in (0, 1, 17, 31, 32, 45, 62, 63):
        for c in range(4):
            Y = (T << 2) | c
            prog = [0xf1, 0xdd, 0xb3, 0x8f, 0xbd]
            for i in range(64):
                prog += [0xd8, 0xb4 | (i >> 4), 0x90 | (i & 15), 0xfc, 0xc0, Y, 0xd9, 0xc0, 0xd8, 0xc2]
            _, ws = run(prog + [0xff])
            got, fl = [], False
            for w in ws:
                if w == M0: fl = True
                elif w == M1:
                    got.append(fl); fl = False
                    if len(got) == 64: break
            exp = [cond[c](v, T) for v in range(64)]
            miss = [v for v in range(64) if v >= len(got) or got[v] != exp[v]]
            total += 64; bad += len(miss)
            print(f"   Y={Y:02x} (field {name[c]} {T:2d}): {64 - len(miss)}/64" + (f"   wrong at {miss[:12]}" if miss else ""))
    print(f"   total {total - bad}/{total} as predicted")

    print("B. bf: where does the store go?")
    def snap():
        h = {(rb, r): d.rd(rb, r)[0] for rb in range(4) for r in range(0x7F) if (rb, r) not in SIDE}
        d.bank(0); return h
    d.mem_write(0x3F0, q32(0xC3) + bytes(12))
    ram1 = d.mem_read(0, 0x4000); h1 = snap()
    for tag, route in (("RAM-routed", 0xdc), ("FIFO-routed", 0xdd)):
        fc, ws = run([0xf1, 0xb3, 0x8f, route, 0xbf, 0xba, 0xa5, 0xc1, 0xff], 10, 16)
        print(f"   {tag}: FIFO count {fc}, head " + " ".join(f"{w:08x}" for w in ws[:4]))
    ram2 = d.mem_read(0, 0x4000); h2 = snap()
    rch = [a for a in range(0x14, 0x4000, 4) if ram1[a:a+4] != ram2[a:a+4] and not (0x1000 <= a < 0x1010)]
    hch = [(k, h1[k], h2[k]) for k in h1 if h1[k] != h2[k] and k not in VOLATILE]
    print("   RAM words changed (outside sensor words and the program): " + (", ".join(f"{a:#06x}={ram2[a:a+4].hex()}" for a in rch[:10]) or "none"))
    print("   host registers changed (non-volatile): " + (", ".join(f"b{k[0]} {k[1]:#04x} {a:02x}->{b:02x}" for k, a, b in hch) or "none"))
    for (rb, r), a, b in hch: d.wr(rb, r, bytes([a]))
    d.bank(0)

    print("C. fc with X < 0xc0")
    d.mem_write(0x3F0, q32(5) + q32(3) + bytes(8))
    d.mem_write(0x3E0, q32(7) + q32(11) + q32(13) + q32(17))
    def cell(tag, mid):
        d.mem_write(0x3D0, bytes(16))
        prog = [0xf1, 0xb3, 0x8f, 0xb7, 0x9e, 0xbb, 0xad, 0xdc, 0xd8] + mid + [0xd9, 0xdd, 0xc0, 0xd8, 0xc2, 0xff]
        _, ws = run(prog, 5, 16)
        page = [int.from_bytes(x, "big") for x in (lambda m: [m[i:i+4] for i in range(0, 16, 4)])(d.mem_read(0x3D0, 16))]
        f = "F" if ws[:1] == [5] else ("-" if ws[:1] == [3] else "?")
        print(f"   {tag:22s} 0x3d0 = {' '.join(str(x) for x in page):16s} F:{f}   fifo {' '.join(str(w) for w in ws[:4])}")
    cell("(nothing)", [])
    cell("10 (ADD alone)", [0x10])
    cell("51 00 (ALU alone)", [0x51, 0x00])
    cell("fc 51 00", [0xfc, 0x51, 0x00])
    cell("fc 51 00 10", [0xfc, 0x51, 0x00, 0x10])
    cell("fc 3d 00", [0xfc, 0x3d, 0x00])
    cell("fc 80 04", [0xfc, 0x80, 0x04])
    cell("fc 08 04", [0xfc, 0x08, 0x04])
    cell("fc c0 00 (field 5 == 0)", [0xfc, 0xc0, 0x00])
    cell("fc c0 14 (field 5 == 5)", [0xfc, 0xc0, 0x14])


if __name__ == "__main__":
    main()
