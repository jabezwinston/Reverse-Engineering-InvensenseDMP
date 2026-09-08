#!/usr/bin/env python3
"""Destination-word probe: which word of the P2 page does a store write, and is the
dest index the store opcode's low nibble (dc/dd/de/df) rather than the ALU op&4 bit?

Model gap (ISA2 Finding 7): operands read any of 4 words (4*A, 4*B), but the store was
only seen to reach P2+0 / P2+4 via op&4 -- words 2,3 of a 16-byte page look unaddressable.
Hypothesis: DINADC family low nibble selects the dest word: dc->+0 dd->+4 de->+8 df->+12,
and op&4 is then a *second ALU bit*, not a destination selector.

Reads all four words 0x240..0x24f after each step. P0=P1=0x70 const page {0.5,0.0,1.0,1.5}.
Distinctive operand: A=2 B=0 -> 1.0 and 0.5, so ADD=+1.5, MUL=+0.5, B-A=-0.5, A-B=+0.5.

    python3 probe8.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q, SITE, SITELEN
from dmpbench import USER_CTRL

P2 = 0x240

class FastRig(Rig):
    def stepw(self, payload):
        b = self.b
        b.mem_write(P2, bytes(16))                                   # scrub all 4 words
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1:
            pass
        b.wr(USER_CTRL, 0x00)
        raw = b.mem_read(P2, 16)
        return [int.from_bytes(raw[4*i:4*i+4], "big") for i in range(4)]

    def safe_stepw(self, payload):
        for _ in range(2):
            try:
                return self.stepw(payload)
            except IOError:
                self.b._reset_and_sync(); self.reinit()
        return None

def show(tag, words):
    if words is None:
        print(f"  {tag}: CRASH", flush=True); return
    cells = " ".join(f"{P2+4*i:#05x}={w:08x}({q(w):+.4f})" for i, w in enumerate(words))
    hit = [i for i, w in enumerate(words) if w]
    print(f"  {tag}: {cells}   -> word {hit if hit else '(none)'}", flush=True)

def main():
    rig = FastRig(sys.argv[1])
    # A=2 B=0 -> operands 1.0, 0.5.  ALU byte = (A<<5)|(B<<3)|op
    A, B = 2, 0
    base = (A << 5) | (B << 3)
    print("== Store-nibble hypothesis: dc/dd/de/df select dest word (ALU op0=ADD, expect +1.5) ==")
    for store in (0xDC, 0xDD, 0xDE, 0xDF):
        show(f"{store:02x} 97 ba a4 {base|0:02x}  (op0 ADD)", rig.safe_stepw([store, 0x97, 0xBA, 0xA4, base | 0]))
    print("== What does op&4 do? dc with op0 vs op4 (same operands) ==")
    show(f"dc ... {base|0:02x}  (op0)", rig.safe_stepw([0xDC, 0x97, 0xBA, 0xA4, base | 0]))
    show(f"dc ... {base|4:02x}  (op4)", rig.safe_stepw([0xDC, 0x97, 0xBA, 0xA4, base | 4]))
    print("== Cross-check: dd with op0 vs op4 -- if nibble is the dest, op4 must NOT move the word ==")
    show(f"dd ... {base|0:02x}  (op0)", rig.safe_stepw([0xDD, 0x97, 0xBA, 0xA4, base | 0]))
    show(f"dd ... {base|4:02x}  (op4)", rig.safe_stepw([0xDD, 0x97, 0xBA, 0xA4, base | 4]))

if __name__ == "__main__":
    main()
