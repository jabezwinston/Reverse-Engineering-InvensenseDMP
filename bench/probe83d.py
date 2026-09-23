#!/usr/bin/env python3
"""P7.4d -- the two residues again, observed in RAM only, one pass per cell.

RAM 0x0014-0x0fff tagged M[a] = 5a000000 | a before every cell.  Each program ends
`d8 f1 e2 ff`, and DMP_INT is the only interrupt, so T stops after exactly one pass.  After the
pass every changed word in 0x0014-0x0fff is listed (tag -> value; a value that is itself a tag
names the word it was copied from).

  A  `bf`: `f1 b3 8f dc bf ba a5 c1` with M[0x3f0] = 000000c3, and controls without bf,
     with bf after the page load, and with two bf.
  B  `fc X Y` for X < 0xc0 as the vendor writes it, with RAM routing:
        f1 dc b3 8c b7 9d bb a8 d8 fc X Y d9 bb a9 f8 d8 f1 e2 ff
     P0 = 0x3c0 [5 3 0 0], P1 = 0x3d0 [7 11 13 17], P2 = 0x380 (tagged); F increments 0x390.
     Also `fc c0 1c` (field 7 == 7, F) and `fc c0 14` (7 == 5, not F) as controls.

    python3 probe83d.py /dev/ttyUSB1
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()
    d.int_config(dmp=True, oflow=False)
    tagged = b"".join(q32(0x5A000000 | a) for a in range(0, 0x1000, 4))

    def cell(tag, prog, seed):
        d.mem_write(0, tagged)
        for a, words in seed.items():
            d.mem_write(a, b"".join(q32(w) for w in words))
        before = d.mem_read(0, 0x1000)
        d.program(prog + [0xd8, 0xf1, 0xe2, 0xff])
        n, us = d.T(20); d.wr(0, USER_CTRL, 0x40)
        after = d.mem_read(0, 0x1000)
        ch = []
        for a in range(0x14, 0x1000, 4):
            if before[a:a+4] != after[a:a+4]:
                v = int.from_bytes(after[a:a+4], "big")
                ch.append(f"{a:#05x}={'@%03x' % (v & 0xfff) if v >> 24 == 0x5A else '%x' % v}")
        print(f"   {tag:26s} ints={n} {us:4d} us  changed: " + (" ".join(ch) or "none"))

    print("A. bf")
    s = {0x3F0: [0xC3, 0, 0, 0]}
    cell("ba a5 c1 (control)", [0xf1, 0xb3, 0x8f, 0xdc, 0xba, 0xa5, 0xc1], s)
    cell("bf ba a5 c1", [0xf1, 0xb3, 0x8f, 0xdc, 0xbf, 0xba, 0xa5, 0xc1], s)
    cell("bf ba a5 c1 (again)", [0xf1, 0xb3, 0x8f, 0xdc, 0xbf, 0xba, 0xa5, 0xc1], s)
    cell("ba a5 bf c1", [0xf1, 0xb3, 0x8f, 0xdc, 0xba, 0xa5, 0xbf, 0xc1], s)
    cell("bf bf ba a5 c1", [0xf1, 0xb3, 0x8f, 0xdc, 0xbf, 0xbf, 0xba, 0xa5, 0xc1], s)
    cell("bf ba a5 d8 f1 ba a5 c1", [0xf1, 0xb3, 0x8f, 0xdc, 0xbf, 0xba, 0xa5, 0xd8, 0xf1, 0xba, 0xa5, 0xc1], s)

    print("B. fc X Y, X < 0xc0 (F -> 0x390 incremented)")
    s = {0x3C0: [5, 3, 0, 0], 0x3D0: [7, 11, 13, 17]}
    head = [0xf1, 0xdc, 0xb3, 0x8c, 0xb7, 0x9d, 0xbb, 0xa8, 0xd8]
    tail = [0xd9, 0xbb, 0xa9, 0xf8, 0xd8]
    for XY in ([], [0xc0, 0x1c], [0xc0, 0x14], [0x51, 0x00], [0x3d, 0x00], [0x80, 0x04], [0x08, 0x04],
               [0x00, 0x00], [0x08, 0x00], [0x10, 0x04]):
        cell("fc " + " ".join(f"{b:02x}" for b in XY) if XY else "(no fc)", head + ([0xfc] + XY if XY else []) + tail, s)
    print("   reference: the same bytes without fc")
    for XY in ([0x51, 0x00], [0x3d, 0x00], [0x08, 0x04]):
        cell(" ".join(f"{b:02x}" for b in XY), head + XY + tail, s)


if __name__ == "__main__":
    main()
