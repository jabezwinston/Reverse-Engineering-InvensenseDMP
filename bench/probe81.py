#!/usr/bin/env python3
"""P7.2 -- can a C compiler target the MPU-6050?  Re-test its control-flow limits with the
DMP3 encodings, which were only learned after Finding 15 closed the question on the MPU.

Custom program at PRGM_START 0x300 (Finding 23), 1 kHz.  A loop body `f8` INCs M[0x240]
(RAM-routed); a runaway pass shows as thousands of INCs per ms, a normal one as ~1/ms.

  A  jump / call forms, the INC at 0x308 and the candidate right after it:
       f4 03 08      DMP3 absolute jump back to the INC        (MPU: 7-bit forward skip of 3)
       f4 43 08      DMP3 call to the INC
       f4 c0 03 08   DMP3 mode-4 two-byte target after a one-byte f4
       e0 after a DMP3 call to a routine `f8 e0` placed at 0x3c0
  B  the MPU bytes never executed by any image (e1, e3-e6, e8-ef): same indirect-addressing
     screen as probe80 C, with the data region below the program tagged M[a] = 5a000000|a
     and the P0 page seeded with small values; plus whether any of them loops.

    python3 probe81.py /dev/ttyUSB0
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
SET = [0xf1, 0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4]      # P0 -> 0x70, P1 -> 0x60, P2 -> 0x240


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0")
    img = dmpinit.dmp_init(b, verbose=False)
    b.wr(SMPLRT_DIV, 0)

    def run(prog, ms=30, n=0, seed=None):
        if seed: seed()
        b.mem_write(0x240, bytes(16))
        b.mem_write(PRGM, bytes(prog))
        b.wr(USER_CTRL, 0x00)
        k, us = (int(x) for x in b.cmd(f"T {ms}").split())
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 4 * n)) if (n and fc) else b""
        b.wr(USER_CTRL, 0x00)
        inc = int.from_bytes(b.mem_read(0x240, 4), "big")
        return inc / (us / 1000), [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)], k, us

    head = SET + [0xdc]                                   # 8 bytes: the INC lands at 0x308
    print("A. control flow, INC/ms (1 = one INC per pass, >> 1 = a loop)")
    b.mem_write(0x3C0, bytes([0xf8, 0xe0, 0xff]))
    cells = [
        ("baseline",        [0xf8]),
        ("f4 03 08",        [0xf8, 0xf4, 0x03, 0x08]),
        ("f4 43 08",        [0xf8, 0xf4, 0x43, 0x08]),
        ("f4 c0 03 08",     [0xf8, 0xf4, 0xc0, 0x03, 0x08]),
        ("f4 00 08",        [0xf8, 0xf4, 0x00, 0x08]),
        ("call 0x3c0",      [0xf8, 0xf4, 0x43, 0xc0, 0xf1, 0xf8]),
        ("jump 0x3c0",      [0xf8, 0xf4, 0x03, 0xc0, 0xf1, 0xf8]),
        ("f4 7f (fwd max)", [0xf8, 0xf4, 0x7f, 0xf8]),
    ]
    for name, body in cells:
        r, _, k, us = run(head + body + [0xd8, 0xff] + [0xff] * 4)
        print(f"   {name:16s} {bytes(body).hex(' '):18s}  {r:8.2f} INC/ms   ints={k} T={us} us")

    print("B. indirect-addressing screen on the unexecuted MPU bytes")
    for a in range(0, 0x300, 16):
        b.mem_write(a, b"".join(q32(0x5A000000 | x) for x in range(a, a + 16, 4)))
    SEED = [0x00000005, 0x00000123, 0x00000200, 0x00000060]

    def seed():
        b.mem_write(0x70, b"".join(q32(w) for w in SEED))
        b.mem_write(0x60, b"".join(q32(0x5A000000 | x) for x in range(0x60, 0x70, 4)))

    def desc(w):
        if w in SEED: return f"s{SEED.index(w)}"
        if w >> 24 == 0x5A: return f"@{w & 0xffffff:03x}"
        return f"{w:08x}"

    for x in [None, 0xe1, 0xe3, 0xe4, 0xe5, 0xe6] + list(range(0xe8, 0xf0)):
        prog = SET + [0xdd] + ([] if x is None else [x]) + [0xd8, 0xd8, 0xd8, 0xf1, 0xc0, 0xc2, 0xc4, 0xc6, 0x00, 0xdc, 0xf8, 0xff, 0xff]
        r, ws, k, us = run(prog, ms=12, n=12, seed=seed)
        print(f"   {'ctrl' if x is None else f'{x:02x}':4s} {r:7.2f} INC/ms  " + " ".join(desc(w) for w in ws[:12]))
    print("   control expectation: s0 s1 s2 s3, then s0 + @060 = 5a000065 (@065)")

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
