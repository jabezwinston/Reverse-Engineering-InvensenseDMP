#!/usr/bin/env python3
"""CMP (f5 op 1) over all sixteen `cmp i,j`, with a distinct value in every operand word.

probe98: with B always word 0, F was set exactly when A < 0, whatever B held -- yet the tilt
filter's `cmp 1,2` and `cmp 3,0` behaved as F := A - B < 0 on silicon.  Here P0 (A) and P1 (B)
hold values chosen so that the candidate rules disagree; the fit is printed.

    python3 probe99.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.host import Rig                 # noqa: E402

ONE = 1 << 30
A = [-ONE // 2, ONE // 4, 3 * ONE // 4, -ONE]          # P0 words: -0.5 0.25 0.75 -1.0
B = [ONE // 2, -ONE // 4, -3 * ONE // 4, ONE]          # P1 words:  0.5 -0.25 -0.75 1.0
MARK = [0x0F0F0F0F, 0x0E0E0E0E]


def main():
    for port in sys.argv[1:] or ["/dev/ttyUSB0"]:
        rig = Rig(port)
        chip = rig.chip
        icm = chip == "icm20948"
        entry = 0x1000 if icm else 0x400
        rig.init(50, 2000, 2)
        rig.b.mem_write(0, bytes(0x3000 if icm else 0xC00))
        if icm:
            rig.reg(2, 0x50, bytes([entry >> 8, entry & 0xFF]))
        else:
            rig.b.wr(0x70, bytes([entry >> 8, entry & 0xFF]))
        for ad, ws in {0x100: A, 0x110: B, 0x3F0: MARK}.items():
            rig.b.mem_write(ad, b"".join((w & 0xFFFFFFFF).to_bytes(4, "big") for w in ws))
        for opname, mode, opc in (("cmp", 0xF5, 1), ("rsub", 0xF1, 1), ("add", 0xF1, 0), ("min", 0xF5, 0),
                                  ("mul", 0xF1, 2)):
          F = {}
          for i in range(4):
            for j in range(4):
                code = ([0xF1, 0xD8] if icm else [0xD8, 0xF1]) + [0xDC, 0xB9, 0xA2, mode, 0xB1, 0x80, 0xB5, 0x91,
                                                                  (i << 5) | (j << 3) | opc]
                code += [0xDD, 0xB3, 0x8F, 0xD9, 0xC0, 0xDA, 0xC2, 0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF]
                rig.b.mem_write(entry, bytes(code))
                if icm:
                    rig.reg(0, 0x68, 0x1F)
                    rig.reg(0, 0x68, 0x1E)
                rig.b.cmd("T 100")
                rig.stop()
                fc = rig.b.fifo_count()
                raw = rig.b.fifo_read(fc) if fc else b""
                F[i, j] = {b"\x0f\x0f\x0f\x0f": True, b"\x0e\x0e\x0e\x0e": False}.get(raw[:4])
          rules = {
            "A - B < 0": lambda i, j: A[i] - B[j] < 0,
            "A < 0": lambda i, j: A[i] < 0,
            "B - A < 0": lambda i, j: B[j] - A[i] < 0,
            "A - P1[i] < 0": lambda i, j: A[i] - B[i] < 0,
            "P0[j] - B < 0": lambda i, j: A[j] - B[j] < 0,
            "A - P0[j] < 0": lambda i, j: A[i] - A[j] < 0,
            "P1[i] - B < 0": lambda i, j: B[i] - B[j] < 0,
            "A + B < 0": lambda i, j: A[i] + B[j] < 0,
            "A < 0 and B >= 0": lambda i, j: A[i] < 0 <= B[j],
            "A > B": lambda i, j: A[i] > B[j],
            "A * B < 0": lambda i, j: A[i] * B[j] < 0,
          }
          print(f"\n{chip}: F after {opname} i,j   (P0 = -0.5 0.25 0.75 -1.0, P1 = 0.5 -0.25 -0.75 1.0)")
          print("        " + "".join(f"  j={j}" for j in range(4)))
          for i in range(4):
            print(f"   i={i}  " + "".join(f"  {'F' if F[i, j] else '-' if F[i, j] is False else '?':>3s}"
                                         for j in range(4)))
          best = sorted(rules, key=lambda n: -sum(F[i, j] == rules[n](i, j) for i in range(4) for j in range(4)))
          print("   best fits: " + ", ".join(f"{n} {sum(F[i, j] == rules[n](i, j) for i in range(4) for j in range(4))}/16"
                                          for n in best[:3]))
        rig.close()


if __name__ == "__main__":
    main()
