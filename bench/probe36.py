#!/usr/bin/env python3
"""Pin down f6 and f7 exactly, in raw hex.

The 4x4 sweep (probe31) showed:
  f6 <alu op0>  = signed MIN(A,B) + 0.00003   -- and 2^-15 = 0.000030518 = 0x00008000 in Q30,
                  which is exactly the round-to-nearest constant for a 16-bit truncation.
  f7 <alu op0>  = a constant, independent of BOTH operands, that printed as +1.97644 with the
                  destination holding the sentinel 0x7E7E7E7E.  Two candidates print the same:
                      0x7E7E0000  = sentinel with the low half-word cleared  (truncate to 16 bits)
                      0x7E7DFE7E  = sentinel - 0x8000                        (subtract the constant)

Distinguish them by starting from a destination whose low half is ALREADY zero: truncation is
then a no-op and the word never changes, while subtracting 0x8000 always changes it.
Everything is reported as raw hex.
    python3 probe36.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R, SENT, LO, N
from dmpbench import USER_CTRL
from isa_probe import q

P = [0x97, 0xBA, 0xA4, 0xDC]          # P0=P1=0x70, P2=0x240, route RAM; `40` stores 1.5


class Raw(R):
    def raw(self, payload, at=1866, seed=None):
        """Run one step and return M[0x240] as a raw 32-bit int (seed it first if asked)."""
        b = self.b
        off = at - 1865
        img = b"\xa3" * off + bytes(payload) + b"\xa3" * (8 - off - len(payload))
        b.mem_write(LO, SENT.to_bytes(4, "big") * (N // 4))
        if seed is not None:
            b.mem_write(0x240, seed.to_bytes(4, "big"))
        b.mem_write(1865, img)
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1:
            pass
        b.wr(USER_CTRL, 0x00)
        return int.from_bytes(b.mem_read(0x240, 4), "big")


def main():
    rig = Raw(sys.argv[1])
    def show(label, payload, seed=None):
        if not rig.control_ok():
            rig.reinit()
        v = rig.raw(P + payload, seed=seed)
        s = f"seed 0x{seed:08X}" if seed is not None else f"seed 0x{SENT:08X} (sentinel)"
        print(f"  {label:26} {s}  ->  0x{v:08X}  ({q(v):+.7f})", flush=True)
        if not rig.control_ok():
            rig.reinit()
        return v

    print("A. f7 with a destination whose low half-word is already zero")
    print("   truncate-to-16 predicts NO CHANGE; subtract-0x8000 predicts seed-0x8000\n")
    for seed in (0x60000000, 0x40000000, 0x12345678, 0x0000FFFF):
        show("f7 00", [0xF7, 0x00], seed=seed)

    print("\nB. f7 after a real store (destination = 1.5, low half zero)")
    show("40 f7", [0x40, 0xF7])
    show("40    (control)", [0x40])

    print("\nC. f6: is the offset exactly 0x00008000?")
    for alu, lbl in ((0x00, "f6 00  min(0.5,0.5)"), (0x28, "f6 28  min(0.0,0.0)"),
                     (0x50, "f6 50  min(1.0,1.0)"), (0x78, "f6 78  min(1.5,1.5)")):
        show(lbl, [0xF6, alu])
    print("\n   f5 controls (should be the exact constants, no offset)")
    for alu, lbl in ((0x00, "f5 00  min(0.5,0.5)"), (0x50, "f5 50  min(1.0,1.0)")):
        show(lbl, [0xF5, alu])

    print("\nD. does f6 round, or just add?  min then truncate should give a rounded 16-bit value")
    show("f6 00 then f7", [0xF6, 0x00, 0xF7])
    show("f5 00 then f7", [0xF5, 0x00, 0xF7])


if __name__ == "__main__":
    main()
