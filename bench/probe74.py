#!/usr/bin/env python3
"""P4.z6 -- f0 is multiplicative.  Clean measurement: every cell starts with f1 (kills the
cross-cell mode leak that contaminated probe72/73), then sets f0 explicitly where tested.

  A=B=0.5 (0x20000000): A+B = 0x40000000, A*B = 0x10000000.
  Body words are one pass; the FIFO repeats the body each pass, so word[i] vs word[i+len]
  shows pass-to-pass carry.

    python3 probe74.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")
def sh(w): return f"{w:08x}"


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = dmpinit.dmp_init(b)
    b.wr(SMPLRT_DIV, 0)
    PTR = [0xf1, 0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4, 0xdd]     # f1 first: mode = 32-bit add

    def cell(body, A=0x20000000, B=0x20000000, n=12):
        b.mem_write(0x70, q32(A) * 4); b.mem_write(0x60, q32(B) * 4)
        b.mem_write(PRGM, bytes(PTR + body + [0xff] * 4))
        b.wr(USER_CTRL, 0x00); b.cmd("T 12"); b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 4 * n)); b.wr(USER_CTRL, 0x00)
        return [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]

    def show(name, body, note=""):
        r = cell(body)
        print(f"  {name:22s} {bytes(body).hex():20s} -> " + " ".join(sh(w) for w in r[:8]) + (f"   | {note}" if note else ""))

    print("control (A=B=0.5: ADD=0x40000000, MUL=0x10000000)")
    show("00 (ADD)", [0x00], "0.5+0.5 = 1.0")
    show("02 (MUL)", [0x02], "0.5*0.5 = 0.25")
    show("f0 00", [0xf0, 0x00], "0.25 if f0 multiplies")
    print("accumulation within a pass (consecutive ops under sticky f0)")
    show("f0 00 00 00 00", [0xf0, 0x00, 0x00, 0x00, 0x00], "0.25 0.5 0.75 1.0 if MAC")
    show("00 00 00 (f1, ADD)", [0x00, 0x00, 0x00], "1.0 1.0 1.0 -- plain ADD does not accumulate")
    show("f0 02 02 02", [0xf0, 0x02, 0x02, 0x02], "does MUL accumulate under f0 too?")
    show("f0 00 f1 00 f0 00", [0xf0, 0x00, 0xf1, 0x00, 0xf0, 0x00], "does f1 in the middle clear the accumulator?")
    show("f0 00 d8 00", [0xf0, 0x00, 0xd8, 0x00], "does d8 clear it? (both under f0)")
    show("f0 00 c0 00", [0xf0, 0x00, 0xc0, 0x00], "does a MOV between clear it?")
    show("f0 00 dc c0 dd 00", [0xf0, 0x00, 0xdc, 0xc0, 0xdd, 0x00], "does a store clear it?")
    print("across passes: is the accumulator reset each pass?  (word[0] of pass 2 = word[len])")
    r = cell([0xf0, 0x00], n=6)
    print(f"  f0 00 alone, many passes -> " + " ".join(sh(w) for w in r[:6]) + "   (all equal = reset each pass)")
    r = cell([0xf0, 0x00, 0x00], n=8)
    print(f"  f0 00 00, many passes    -> " + " ".join(sh(w) for w in r[:8]) + "   (pass boundary every 2 words)")
    print("op field under f0 (A=1.25=0x50000000, B=1.0=0x40000000; MUL=0x50000000)")
    for op in range(8):
        show(f"f0 {op:02x}", [0xf0, op], "", )
    print("  same, fresh MUL/NMUL for reference")
    show("02 (MUL 1.25*1.0)", [0x02])
    show("03 (NMUL)", [0x03])
    print("what the accumulator holds: f0 08 (A0*B1) then f0 10 (A0*B2) -- sum of two products?")
    b.mem_write(0x70, b"".join(q32(x) for x in (0x20000000, 0, 0, 0)))
    b.mem_write(0x60, b"".join(q32(x) for x in (0x40000000, 0x20000000, 0x10000000, 0x08000000)))
    b.mem_write(PRGM, bytes(PTR + [0xf0, 0x00, 0x08, 0x10, 0x18] + [0xff] * 4))
    b.wr(USER_CTRL, 0x00); b.cmd("T 12"); b.wr(USER_CTRL, 0x40)
    fc = b.fifo_count(); raw = b.fifo_read(min(fc, 20)); b.wr(USER_CTRL, 0x00)
    ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw)-3, 4)]
    print("  A=0.5; B=[1,0.5,0.25,0.125]; f0 00 08 10 18 -> " + " ".join(sh(w) for w in ws[:5]))
    print("     products 0.5, 0.25, 0.125, 0.0625; cumulative 0.5,0.75,0.875,0.9375 = 20000000 30000000 38000000 3c000000")

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
