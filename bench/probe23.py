#!/usr/bin/env python3
"""16-bit store hypothesis for f8/f9/fa/fb and df, with RAW HEX and a distinctive accumulator.
  96 ba a4 dc 10 <X>  : P1=page6, op 10 = A0(0.5)+B2(0x02CB47A2) -> acc 0x22CB47A2 (halves 22CB / 47A2)
  Sentinel 7E7E7E7E: a half-word write leaves the other half as 7E7E.
  Also 97-page acc 1.5 (6000_0000) and -0.5 (E000_0000) for df/fa, and 'X alone' (no op).
    python3 probe23.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R
SENT = 0x7E7E7E7E

def hexfmt(h):
    if h is None: return "CRASH"
    return " ".join(f"{a:#x}={v:08x}" for a,v in sorted(h.items()) if a < 0x270) or "nothing"

def guarded_hex(rig, label, payload, at=1866):
    if not rig.control_ok():
        rig.reinit()
        if not rig.control_ok(): print(f"  {label}: CONTROL FAILED"); return
    r = hexfmt(rig.safe(payload, at)); scr = ""
    if not rig.control_ok(): rig.reinit(); scr = "   [POISONS]"
    print(f"  {label:22} {r}{scr}", flush=True)

def main():
    rig = R(sys.argv[1])
    Q = [0x96,0xBA,0xA4,0xDC,0x10]      # acc = 22CB47A2
    P = [0x97,0xBA,0xA4,0xDC]
    print("== acc 22CB47A2, then X ==")
    guarded_hex(rig, "10 (ctrl)", Q)
    for X in (0xF8,0xF9,0xFA,0xFB,0xDF):
        guarded_hex(rig, f"10 {X:02x}", Q+[X])
    print("== acc 6000_0000 / E000_0000 ==")
    for name, pl in (("40 f8", P+[0x40,0xF8]), ("40 f9", P+[0x40,0xF9]), ("40 fb", P+[0x40,0xFB]),
                     ("41 fa", P+[0x41,0xFA]), ("41 f9", P+[0x41,0xF9])):
        guarded_hex(rig, name, pl)
    print("== X alone (no op in block) ==")
    for X in (0xF8,0xF9,0xFA,0xFB):
        guarded_hex(rig, f"{X:02x} alone", P+[X])

if __name__ == "__main__":
    main()
