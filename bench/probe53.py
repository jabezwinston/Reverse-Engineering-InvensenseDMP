#!/usr/bin/env python3
"""P6.9 -- e2, e7 and the FSYNC pin on DMP3.

  e2  raises DMP_INT1: the bridge's T returns at the first INT1 edge, ~0.4 ms after the
      start instead of at its timeout, with INT_STATUS bit 1 set; under d9 it fires only
      when F is set.  This is the vendor's `da f0 e2 f1` (IF.NZ interrupt) at 0x23ec.
  e7  clears M[P2] in place, indistinguishable from de in every cell (one vendor site).
  FSYNC (ESP32 D4, bridge command Y): with EXT_SYNC_SET = 1 the level shows in TEMP_OUT_L
      bit 0, so the wire is good -- and neither e7 nor db follows it.

    python3 probe53.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

MARK = 0x33333333
FSYNC_CONFIG = 0x52     # bank 2


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, q32(0) + q32(1) + q32(0xFFFFFFFF) + q32(MARK))
    H = [0xf1, 0xb3, 0x8f, 0xb7, 0x9f, 0xdd]
    R = [0xf1, 0xb3, 0x8f, 0xb7, 0x9f, 0xbb, 0xad, 0xdc]

    def T(prog, ms=50):
        d.program(prog + [0xd8, 0xff]); d.fifo_reset(); n, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        return n, us, d.fifo_count(), d.int_status()

    print("A. e2 = DMP_INT1")
    for name, prog in (("no e2", H + [0x08, 0xd1, 0xc4, 0xc6]), ("e2", H + [0x08, 0xd1, 0xe2, 0xc4, 0xc6]),
                       ("d9 e2, F=0", H + [0x08, 0xd1, 0xd9, 0xe2, 0xd8, 0xc4]), ("d9 e2, F=1", H + [0x00, 0xd1, 0xd9, 0xe2, 0xd8, 0xc4]),
                       ("e7", H + [0x08, 0xd1, 0xe7, 0xc4, 0xc6])):
        n, us, fc, st = T(prog)
        print(f"   {name:12s} T(50): ints={n} dt={us:6d} us  fifo={fc:4d}  INT_STATUS={st.hex()}  {'<- INT1 from the DMP' if n and us < 5000 else ''}")

    print("B. e7 vs de under RAM routing (P2 = 0x3d0 seeded c0ffee00)")
    for name, prog in (("c4", R + [0xc4]), ("c4 e7", R + [0xc4, 0xe7]), ("c4 de", R + [0xc4, 0xde]), ("c4 e7 c6", R + [0xc4, 0xe7, 0xc6]), ("c4 e2", R + [0xc4, 0xe2])):
        d.mem_write(0x3D0, q32(0xC0FFEE00) * 4)
        d.program(prog + [0xd8, 0xff]); d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
        m = d.mem_read(0x3D0, 8)
        print(f"   {name:10s} 0x3d0: {m[:4].hex()} {m[4:].hex()}")

    print("C. FSYNC on D4")
    for cfg in (0x00, 0x01):
        d.wr(2, FSYNC_CONFIG, cfg)
        for lvl in (0, 1):
            d.b.cmd(f"Y {lvl}")
            temp_l = d.rd(0, 0x3A)[0]
            d.mem_write(0x3D0, q32(0xC0FFEE00))
            d.program(R + [0xc4, 0xe7, 0xd8, 0xff]); d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
            e7 = int.from_bytes(d.mem_read(0x3D0, 4), "big")
            d.program(H + [0x08, 0xd1, 0xdb, 0xc6, 0xd8, 0xff]); d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
            fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 8)))
            print(f"   EXT_SYNC_SET={cfg} D4={lvl}: TEMP_OUT_L bit0={temp_l & 1}   e7 stores {e7:08x}   db (F=0) {'taken' if MARK in ws[:2] else 'skipped'}")
    d.wr(2, FSYNC_CONFIG, 0); d.b.cmd("Y 0")


if __name__ == "__main__":
    main()
