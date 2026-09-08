#!/usr/bin/env python3
"""End-to-end: assemble with tools/dmpasm.py, run the bytes on silicon, verify the
committed Q30 word. Also checks whether the store works with dc emitted AFTER the
pointer setup (the assembler's natural order) vs dc-first (the optable order).

P0 stays at the host image's 0x70 const page {0.5,0.0,1.0,1.5}. The 5-byte site holds:
    97 a4 ba dc <v>     (p1page7, p2page4, p2bank2 -> P2=0x240, store.<op> A,B)
Prediction = op(cA,cB) in Q30 with wrap to [-2,+2).

    python3 probe9.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from isa_probe import Rig, q, SITE, SITELEN
from dmpbench import USER_CTRL
from dmpasm import assemble
import time

P2 = 0x240
C = {0: 0.5, 1: 0.0, 2: 1.0, 3: 1.5}
def wrap(x): return ((x + 2) % 4) - 2
PRED = {"add": lambda a,b: wrap(C[a]+C[b]), "rsub": lambda a,b: wrap(C[b]-C[a]),
        "mul": lambda a,b: wrap(C[a]*C[b]), "nmul": lambda a,b: wrap(-C[a]*C[b])}

class FastRig(Rig):
    def run_bytes(self, payload):
        b = self.b
        b.mem_write(P2, bytes(4))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1:
            pass
        b.wr(USER_CTRL, 0x00)
        return int.from_bytes(b.mem_read(P2, 4), "big")
    def safe(self, payload):
        for _ in range(2):
            try: return self.run_bytes(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def main():
    rig = FastRig(sys.argv[1])
    cases = [("add",2,0),("rsub",2,0),("mul",3,0),("nmul",3,0),
             ("add",2,3),("mul",2,3),("rsub",0,2),("add",3,3)]
    print(f"{'source':24} {'asm bytes':14} {'measured':>12} {'predict':>9}  ok")
    ok = 0
    for op,A,B in cases:
        src = f".lineage mantis\np1page 7\np2page 4\np2bank 2\nstore.{op} {A},{B}\n"
        payload = assemble(src)
        v = rig.safe(payload)
        if v is None:
            print(f"store.{op} {A},{B:<15} {payload.hex(' ')}  CRASH"); continue
        got, pred = q(v), PRED[op](A,B)
        good = abs(got-pred) < 2e-3
        ok += good
        print(f"store.{op} {A},{B:<15} {payload.hex(' '):14} {v:08x} {got:+.4f} {pred:+9.4f}  {'YES' if good else 'no'}")
    # ordering check: dc-first vs assembler order, same op
    print("\nordering check (add 2,0, expect +1.5):")
    asm = assemble(".lineage mantis\np1page 7\np2page 4\np2bank 2\nstore.add 2,0\n")
    dcfirst = bytes([0xDC,0x97,0xBA,0xA4,0x40])
    for tag,pl in (("assembler (…dc 40)",asm),("optable   (dc … 40)",dcfirst)):
        v = rig.safe(pl)
        print(f"  {tag}: {pl.hex(' ')} -> {v:08x} ({q(v):+.4f})" if v is not None else f"  {tag}: CRASH")
    print(f"\n{ok}/{len(cases)} cells match prediction")

if __name__ == "__main__":
    main()
