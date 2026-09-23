#!/usr/bin/env python3
"""RSUB's F where B - A overflows: is it the exact sign (Finding 37) or the wrapped word's?
The compiler compares with `rsub` into a scratch word (probe99: CMP tests signs only).

    python3 probe100.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.host import Rig                 # noqa: E402

ONE = 1 << 30
PAIRS = [(-3 * ONE // 2, 3 * ONE // 2), (3 * ONE // 2, -3 * ONE // 2), (-2 * ONE, 0), (0, -2 * ONE),
         (-2 * ONE, 2 * ONE - 1), (2 * ONE - 1, -2 * ONE), (ONE, ONE), (-1, 0), (0, -1), (1, 0)]
MARK = [0x0F0F0F0F, 0x0E0E0E0E]


def main():
    for port in sys.argv[1:] or ["/dev/ttyUSB0"]:
        rig = Rig(port)
        icm = rig.chip == "icm20948"
        entry = 0x1000 if icm else 0x400
        rig.init(50, 2000, 2)
        rig.b.mem_write(0, bytes(0x3000 if icm else 0xC00))
        if icm:
            rig.reg(2, 0x50, bytes([entry >> 8, entry & 0xFF]))
        else:
            rig.b.wr(0x70, bytes([entry >> 8, entry & 0xFF]))
        rig.b.mem_write(0x3F0, b"".join(w.to_bytes(4, "big") for w in MARK))
        print(f"\n{rig.chip}: rsub A,B (B - A) where it overflows")
        ok = 0
        for a, b in PAIRS:
            rig.b.mem_write(0x100, (a & 0xFFFFFFFF).to_bytes(4, "big"))
            rig.b.mem_write(0x110, (b & 0xFFFFFFFF).to_bytes(4, "big"))
            code = ([0xF1, 0xD8] if icm else [0xD8, 0xF1]) + [0xDC, 0xB9, 0xA2, 0xB1, 0x80, 0xB5, 0x91, 0x01]
            code += [0xDD, 0xB3, 0x8F, 0xD9, 0xC0, 0xDA, 0xC2, 0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF]
            rig.b.mem_write(entry, bytes(code))
            if icm:
                rig.reg(0, 0x68, 0x1F)
                rig.reg(0, 0x68, 0x1E)
            rig.b.cmd("T 100")
            rig.stop()
            raw = rig.b.fifo_read(rig.b.fifo_count())
            f = {b"\x0f\x0f\x0f\x0f": True, b"\x0e\x0e\x0e\x0e": False}.get(raw[:4])
            exact = (b - a) < 0
            wrapped = ((b - a + (1 << 31)) % (1 << 32) - (1 << 31)) < 0
            stored = int.from_bytes(rig.b.mem_read(0x120, 4), "big")
            ok += f == exact
            print(f"  A {a / ONE:+.9f}  B {b / ONE:+.9f}  B-A {(b - a) / ONE:+.9f}: F {'set' if f else 'clear'}"
                  f"  (exact sign {'set' if exact else 'clear'}, wrapped {'set' if wrapped else 'clear'})"
                  f"  stored {stored:08x}")
        print(f"  {ok}/{len(PAIRS)} follow the exact sign")
        rig.close()


if __name__ == "__main__":
    main()
