#!/usr/bin/env python3
"""Where does the MPU-6050's mode-4 jump land?

Finding 40: after any `f4` the MPU is in mode 4, and a byte below 0x80 plus the byte after it
jump somewhere (`14 20` and `0c 20` reached 0x420, `04 20` fell through).  Mapped, this would give
the MPU an absolute jump, and spare compiled code its chains of branch hops.

A counting sled of INC (f8, which runs in mode 4) fills 0x010-0xbdb and ends in `d8 fe ff`.
P2 points at word 0x00c, whose low half (0x00e-0x00f) the hardware never writes (Finding 39):
the sled counts there.  The harness sits at 0xbe0, above the sled: it clears the count, enters
mode 4 with `f4 00`, executes `hi lo`, and ends in `d8 fe ff` for a fall-through.  A landing at X
in the sled leaves the count at 0xbdc - X.  Landing in 0x000-0x00f runs sensor bytes.

    python3 probe104.py /dev/ttyUSB0 [lo ...]
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.host import Rig                 # noqa: E402

SLED, END = 0x010, 0xBDC
HARNESS = 0xBE0


def run(rig, hi, lo, pre=(0xF4, 0x00)):
    # always; 32-bit; RAM; P2 -> 0x000 (word 0), + 2, then clr.next under f3: word 3 (0x00c),
    # low half cleared -- the count
    code = [0xD8, 0xF1, 0xDC, 0xB8, 0xA0, 0xD0, 0xF3, 0xDF, 0xF1] + list(pre) + \
        [hi, lo, 0xD8, 0xFE, 0xFF, 0xFF]
    rig.b.mem_write(HARNESS, bytes(code))
    n, _ = map(int, rig.b.cmd("T 60").split())
    rig.stop()
    c = int.from_bytes(rig.b.mem_read(0x00E, 2), "big")
    return n, c


def main():
    port = next((a for a in sys.argv[1:] if a.startswith("/dev/")), "/dev/ttyUSB0")
    los = [int(a, 0) for a in sys.argv[1:] if not a.startswith("/dev/")] or [0x20, 0x00, 0x81, 0xFF]
    rig = Rig(port)
    if rig.chip != "mpu6050":
        raise SystemExit("MPU-6050 only")
    rig.init(50, 2000, 2)
    rig.b.mem_write(0, bytes(0xC00))
    rig.b.mem_write(SLED, bytes([0xF8] * (END - SLED)) + bytes([0xD8, 0xFE, 0xFF, 0xFF]))
    rig.b.wr(0x70, bytes([HARNESS >> 8, HARNESS & 0xFF]))
    for lo in los:
        print(f"\nlo = {lo:02x}: hi -> landing (INT count in 60 ms)")
        row = []
        for hi in range(0x80):
            n, c = run(rig, hi, lo)
            land = END - c if c else None
            if n == 0:
                txt = "no INT"
            elif c == 0:
                txt = "fell through" if n else "?"
            else:
                txt = f"{land:#05x}"
            row.append(f"{hi:02x}:{txt}")
        for k in range(0, 128, 8):
            print("  " + "  ".join(f"{x:16s}" for x in row[k:k + 8]))
    rig.close()


if __name__ == "__main__":
    main()
