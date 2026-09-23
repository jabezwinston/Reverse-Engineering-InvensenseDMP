#!/usr/bin/env python3
"""P7.2b -- probe81's two contaminated cells, redone so no store can reach the counter.

The counter M[0x240] is re-pointed by the `a4` at 0x306 (SET's last byte), so a DMP3-style
target of 0x0306 re-enters `a4 dc f8`.  Every byte that would execute on the MPU instead of
being a target half is a P2 load (`a5` -> 0x250) or an ALU op storing through it, so a
non-jump leaves the counter at one INC per pass.  DMP_INT is masked (INT_ENABLE = FIFO_OFLOW
only) so `f4 4x` cannot end the T window.

  A1  f4 a5 03 06          DMP3 mode-4: target 0x0306 -> loop.  MPU: a5, then 03 06 ALU into 0x250
  A2  f4 43 a5  + routine at 0x3a5 = `a4 dc f8 e0`
                           DMP3 call -> 2 INC/pass.  MPU: f4 4x interrupt form, a5 runs
  A3  a5 03 06             the same bytes without f4 (reference)
  A4  f4 a5  d8 03 06      mode entered, d8 in between, then the low pair
  B   P2 after each unexecuted byte (0x3c0 should read 600d600d)

    python3 probe81b.py /dev/ttyUSB0
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
SET = [0xf1, 0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4]      # P0 -> 0x70, P1 -> 0x60, P2 -> 0x240
INT_ENABLE = 0x38


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0")
    img = dmpinit.dmp_init(b, verbose=False)
    b.wr(SMPLRT_DIV, 0)
    b.wr(INT_ENABLE, 0x10)

    def run(prog, ms=30):
        b.mem_write(0x240, bytes(16)); b.mem_write(0x250, bytes(16))
        b.mem_write(PRGM, bytes(prog))
        b.wr(USER_CTRL, 0x00)
        k, us = (int(x) for x in b.cmd(f"T {ms}").split())
        b.wr(USER_CTRL, 0x00)
        inc = int.from_bytes(b.mem_read(0x240, 4), "big")
        return inc, us, k

    head = SET + [0xdc, 0xf8]                            # a4 at 0x306, dc 0x307, INC 0x308
    b.mem_write(0x3A5, bytes([0xa4, 0xdc, 0xf8, 0xe0, 0xff]))
    print("A. INC count over a 30 ms window (~30 = one INC per pass)")
    for name, body in [("baseline", []),
                       ("A1 f4 a5 03 06", [0xf4, 0xa5, 0x03, 0x06]),
                       ("A2 f4 43 a5", [0xf4, 0x43, 0xa5]),
                       ("A3 a5 03 06", [0xa5, 0x03, 0x06]),
                       ("A4 f4 a5 d8 03 06", [0xf4, 0xa5, 0xd8, 0x03, 0x06]),
                       ("A5 f4 03 06", [0xf4, 0x03, 0x06])]:
        inc, us, k = run(head + body + [0xd8, 0xff, 0xff, 0xff])
        print(f"   {name:20s} INC={inc:6d} in {us} us  ({inc / (us / 1000):5.2f}/ms)  ints={k}")

    print("B. P2 after each unexecuted byte (0x3c0 should read 600d600d)")
    b.mem_write(0x70, q32(0x600D600D) + bytes(12))
    for x in [None, 0xe1, 0xe3, 0xe4, 0xe5, 0xe6] + list(range(0xe8, 0xf0)):
        b.mem_write(0x2C0, b"".join(q32(0x5A000000 | a) for a in range(0x2C0, 0x2D0, 4)))
        # P2 -> bank 2 page c = 0x2c0 (0x3c0 is inside the program window)
        prog = [0xf1, 0xb0, 0x87, 0xba, 0xac, 0xdc] + ([] if x is None else [x]) + [0xd8, 0xd8, 0xd8, 0xf1, 0xdc, 0xc0, 0xff, 0xff]
        run(prog, 10)
        got = b.mem_read(0x2C0, 16)
        where = ""
        if got[:4] != q32(0x600D600D):
            mem = b.mem_read(0, 0x300)
            hits = [a for a in range(0, 0x300, 4) if mem[a:a+4] == q32(0x600D600D) and a != 0x70]
            where = "  found at " + (", ".join(f"{a:#05x}" for a in hits) or "nowhere")
        print(f"   {'ctrl' if x is None else f'{x:02x}':4s}  0x2c0 = " +
              " ".join(got[i:i+4].hex() for i in range(0, 16, 4)) + where)

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
