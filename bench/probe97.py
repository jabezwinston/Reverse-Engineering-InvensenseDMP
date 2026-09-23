#!/usr/bin/env python3
"""Does the MPU-6050 have DMP3's mode 4: after any f4, a byte below 0x80 and the next are a
two-byte jump (or, with bit 14, a call)?

probe96: after an f4, every ALU op seemed to store nothing, and a MOV after an `add ..,inc` in
mode 4 stored nowhere in its page -- as if control went elsewhere.  The vendor's MotionApps 6.12
images branch to `14 14` right after an f4 (2639 image, 0x55a).

Each cell: code at 0x400 enters mode 4 with an f4, then two low bytes X Y; the fall-through
emits marker A.  Marker programs at candidate targets emit their own marker and interrupt.
Markers come from src 0x100 = [a0a0a0a0, b1b1b1b1, c2c2c2c2, d3d3d3d3].

    python3 probe97.py /dev/ttyUSB0
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.host import Rig                 # noqa: E402

SRC = [0xA0A0A0A0, 0xB1B1B1B1, 0xC2C2C2C2, 0xD3D3D3D3]


def marker(k):
    """d8 f1 dd, P0 -> 0x100, emit word k, int, end"""
    return bytes([0xD8, 0xF1, 0xDD, 0xB1, 0x80, 0xC0 | (k << 1), 0xFE, 0xFF])


# candidate targets: 0x420 (B), 0x820 (C), 0x620 (D)
TARGETS = {0x420: 1, 0x820: 2, 0x620: 3}
CELLS = [
    ("f4 00, 04 20 (jump 0x420?)",       [0xF4, 0x00, 0x04, 0x20]),
    ("f4 00, 08 20 (jump 0x820?)",       [0xF4, 0x00, 0x08, 0x20]),
    ("f4 00, 14 20 (0x1420 -> ?)",       [0xF4, 0x00, 0x14, 0x20]),
    ("f4 00, 0c 20 (0xc20 -> ?)",        [0xF4, 0x00, 0x0C, 0x20]),
    ("f4 80.., 04 20 (1-byte f4)",       [0xF4, 0xB0, 0x04, 0x20]),
    ("f4 00, f1, 04 20 (mode 1: add)",   [0xF4, 0x00, 0xF1, 0x04, 0x20]),
    ("f4 00, 44 20 (call 0x420?)",       [0xF4, 0x00, 0x44, 0x20]),
    ("no f4: f1 04 20 (control)",        [0xF1, 0x04, 0x20]),
]


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    rig = Rig(port)
    if rig.chip != "mpu6050":
        raise SystemExit("MPU-6050 only")
    rig.init(50, 2000, 2)
    rig.b.mem_write(0, bytes(0xC00))
    rig.b.wr(0x70, bytes([0x04, 0x00]))
    rig.b.mem_write(0x100, b"".join(w.to_bytes(4, "big") for w in SRC))
    for addr, k in TARGETS.items():
        rig.b.mem_write(addr, marker(k))
    names = {0xA0A0A0A0: "fell through (A)", 0xB1B1B1B1: "0x420 (B)", 0xC2C2C2C2: "0x820 (C)",
             0xD3D3D3D3: "0x620 (D)"}
    print("mpu6050: where control goes after an f4 and two low bytes")
    for label, body in CELLS:
        code = bytes([0xD8, 0xF1, 0xDC] + body + [0xD8]) + marker(0)
        rig.b.mem_write(0x400, code)
        n, us = map(int, rig.b.cmd("T 100").split())
        rig.stop()
        fc = rig.b.fifo_count()
        raw = rig.b.fifo_read(fc) if fc else b""
        ws = [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw) - 3, 4)]
        where = ", ".join(names.get(w, f"{w:08x}") for w in ws) or "nothing emitted"
        print(f"  {label:34s} INT {n}  ->  {where}")
    rig.close()


if __name__ == "__main__":
    main()
