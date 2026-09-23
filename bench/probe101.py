#!/usr/bin/env python3
"""Where does the MPU-6050's `f4 d` land, for every d in 0..63?

opendmp's first long branches (a 1.7 KB program with 45 branch hops) went somewhere other than
+2+d on silicon; earlier probes (26/27/69/70) used short displacements.  After `f4 d` sit 64
`inc` bytes (f8: one byte, runs in any mode) and an end: the counter at 0x100 reads 64 minus
the landing offset.  Also with the branch skipped by a false predicate.

    python3 probe101.py /dev/ttyUSB0
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.host import Rig                 # noqa: E402


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    rig = Rig(port)
    if rig.chip != "mpu6050":
        raise SystemExit("MPU-6050 only")
    rig.init(50, 2000, 2)
    rig.b.mem_write(0, bytes(0xC00))
    rig.b.wr(0x70, bytes([0x04, 0x00]))
    head = [0xD8, 0xF1, 0xDC, 0xB9, 0xA0, 0xDE]          # RAM, P2 -> 0x100, clear the counter
    sled = [0xF8] * 64 + [0xD8, 0xFE, 0xFF, 0xFF]
    print("mpu6050: f4 d (taken) -> landing offset after the instruction; then skipped under a false d9")
    wrong = []
    for d in range(64):
        rig.b.mem_write(0x400, bytes(head + [0xF4, d] + sled))
        n, _ = map(int, rig.b.cmd("T 100").split())
        rig.stop()
        c = int.from_bytes(rig.b.mem_read(0x100, 4), "big")
        land = 64 - c if n else None
        if land != d:
            wrong.append((d, land, n))
        print(f"  f4 {d:02x}: lands +{land if land is not None else '?'}  (INT {n})" + ("" if land == d else "  <<<"))
    print(f"  {64 - len(wrong)}/64 land at +d")
    # backward? jump forward over a 24-inc sled, then f4 d (0x20-0x3f) from past its end
    print("\n  f4 20-3f: taken from 0x424, past a sled of 24 incs at 0x408-0x41f (end at 0x420)")
    for d in range(0x20, 0x40):
        code = head + [0xF4, 0x1C] + [0xF8] * 24 + [0xD8, 0xFE, 0xFF, 0xFF] + [0xF4, d, 0xD8, 0xFE, 0xFF, 0xFF]
        rig.b.mem_write(0x400, bytes(code))
        n, _ = map(int, rig.b.cmd("T 100").split())
        rig.stop()
        c = int.from_bytes(rig.b.mem_read(0x100, 4), "big")
        land = 0x420 - c if n else None
        guess = 0x426 + (d - 64)
        print(f"  f4 {d:02x}: " + (f"landed {land:#05x} = f4 + 2 {land - 0x426:+d}" if land is not None and c
                                    else f"counter {c}, INT {n}") + f"   (d - 64 = {d - 64}: {guess:#05x})")
    # skipped: F is set by the clear? use rsub 0,0 of zeros -> F clear, then d9 (if F) is false
    for d in (0, 2, 3, 0x12, 0x3C):
        rig.b.mem_write(0x400, bytes(head + [0xF1, 0x01, 0xD9, 0xF4, d, 0xD8] + sled))
        n, _ = map(int, rig.b.cmd("T 100").split())
        rig.stop()
        c = int.from_bytes(rig.b.mem_read(0x100, 4), "big")
        print(f"  skipped f4 {d:02x}: counter {c} (64 = the whole sled ran)  INT {n}")
    rig.close()


if __name__ == "__main__":
    main()
