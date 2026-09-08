#!/usr/bin/env python3
"""Can the DMP loop?  f4 imm with imm >= 0x80: signed (backward) or something else?
Body = INC M[0x240] once per pass.  Window 1865..1872:
    1865 a4  1866 ba  1867 dc  1868 f8  1869 f4  1870 <imm>  1871 a3  1872 a3
f4 sits at 1869, so target = 1871 + imm.  Signed: imm 0xFF -> 1870 (the imm byte),
0xFE -> 1869 (self), 0xFD -> 1868 (re-run the INC = a tight loop).
Detectors: interrupts in the window (a hang -> ~0) and M[0x240], which counts INC executions.
Baseline (no branch) gives one INC per DMP pass.   python3 probe26.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig
from dmpbench import USER_CTRL
WIN, WLEN, P2 = 1865, 8, 0x240

class R(Rig):
    def run(self, payload):
        b = self.b
        b.mem_write(P2, bytes(4))
        b.mem_write(WIN, bytes(payload) + b"\xa3" * (WLEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        time.sleep(0.35)
        b.wr(USER_CTRL, 0x00)
        ints = b.int_state()[1]
        return ints, int.from_bytes(b.mem_read(P2, 4), "big")
    def safe(self, payload):
        for _ in range(2):
            try: return self.run(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None
    def ok(self):
        r = self.safe([0xA4,0xBA,0xDC,0xF8]); return r is not None and r[0] > 20

def main():
    rig = R(sys.argv[1])
    base = [0xA4,0xBA,0xDC,0xF8]
    r = rig.safe(base)
    print(f"  baseline (no branch)   ints={r[0]:4} M[0x240]={r[1]:08x} ({r[1]} INCs)")
    r = rig.safe(base+[0xF4,0x02])
    print(f"  f4 02 (forward, known) ints={r[0]:4} M[0x240]={r[1]:08x}")
    print("  --- imm >= 0x80 ---")
    for imm in (0xFF,0xFE,0xFD,0xFC,0xF8,0xF0,0xE0,0xC0,0xA0,0x90,0x88,0x80):
        rr = []
        for _ in range(2):
            x = rig.safe(base+[0xF4,imm]); rr.append(x)
            if not rig.ok():
                rig.reinit()
        if any(x is None for x in rr): print(f"  f4 {imm:02x}  CRASH"); continue
        tgt_s = 1871 + (imm - 256)
        print(f"  f4 {imm:02x}  ints={rr[0][0]:4}/{rr[1][0]:<4} M[0x240]={rr[0][1]:08x}/{rr[1][1]:08x}"
              f"   signed target -> {tgt_s}", flush=True)

if __name__ == "__main__":
    main()
