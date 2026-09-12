#!/usr/bin/env python3
"""P6.3 -- do the mantis semantics transfer to the ICM-20948's DMP3 core?

Custom programs at 0x1000 (the vendor entry point), data words planted at
P = bank 3, page 15 = 0x3f0 (mantis addressing, inside the ICM's 16 KB), FIFO routing.
Each cell is one T-timed run: the program only emits, so the first INT1 is the FIFO
overflow -- the ICM FIFO is 4096 B, so 1024 passes -- and the FIFO head shows what the
first passes produced.

  A. MOV:    b3 8f dd f1 c0 ff            expect w0 every pass, 4 B/pass, 1024 passes
  B. ALU:    b3 8f b7 9f dd f1 <op> ff    add/rsub/mul/nmul of w1 (A=1) and w0 (B=0)
  C. RAM:    b3 8f b7 9f bb ae dc f1 20 c1 ff   sum -> M[0x3e0], then MOV w0 -> M[0x3e4]
  D. branch: b3 8f dd f1 c0 f4 01 c2 c4 ff      skip c2: 8 B/pass = w0 w2
  E. width:  b3 8f dd f2 c0 ff / f3        16-bit stores: 2 B/pass

First run of this probe used b0 (bank 0) by mistake and read the vendor image's
constants at 0xf0 -- 00080008 and 00040004 -- and the add returned 000c000c: correct
arithmetic on the wrong page, which is how the mistake was caught.

    python3 probe44.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

P = 0x3F0
W = [0x10000000, 0x20000000, 0x33333333, 0x44444444]      # w0..w3 at P


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(P, b"".join(q32(w) for w in W))
    d.mem_write(0x3E0, bytes(16))

    def cell(name, prog, nbytes=32):
        d.program(prog)
        n, us, fc, raw = d.run_capture(nbytes=nbytes)
        ws = d.words(raw)
        print(f"{name:8s} {bytes(prog).hex():28s} ints={n} dt={us:7d} us fifo={fc:4d}  " +
              " ".join(f"{w:08x}" for w in ws[:6]))
        return n, us, fc, raw

    print("A. MOV to FIFO")
    cell("mov w0", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xff])
    cell("mov w2", [0xb3, 0x8f, 0xdd, 0xf1, 0xc4, 0xff])
    cell("mov16", [0xb3, 0x8f, 0xdd, 0xf1, 0xcc, 0xff])

    print("B. ALU (A=w1, B=w0)")
    exp = {"add": (W[1] + W[0]), "rsub": (W[0] - W[1]), "mul": (W[1] * W[0]) >> 30, "nmul": -((W[1] * W[0]) >> 30)}
    for i, name in enumerate(("add", "rsub", "mul", "nmul")):
        n, us, fc, raw = cell(name, [0xb3, 0x8f, 0xb7, 0x9f, 0xdd, 0xf1, 0x20 | i, 0xff])
        got = d.words(raw)[:1]
        print(f"         expect {exp[name] & 0xFFFFFFFF:08x}  {'MATCH' if got and got[0] == (exp[name] & 0xFFFFFFFF) else 'DIFF'}")

    print("C. RAM route, P2 = bank 3 page 14 = 0x3e0")
    d.program([0xb3, 0x8f, 0xb7, 0x9f, 0xbb, 0xae, 0xdc, 0xf1, 0x20, 0xc1, 0xff])
    n, us = d.T(100)
    d.wr(0, USER_CTRL, 0x40)
    m = d.mem_read(0x3E0, 16)
    print(f"   ints={n} (expect 0: nothing emitted)  M[0x3e0..] = {m.hex()}  expect {W[1]+W[0]:08x} {W[0]:08x}")

    print("D. branch f4 01 over c2")
    cell("branch", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x01, 0xc2, 0xc4, 0xff], nbytes=32)
    print("   expect w0 w2 w0 w2 ... and dt half of A")

    print("E. store width")
    cell("f2", [0xb3, 0x8f, 0xdd, 0xf2, 0xc0, 0xff], nbytes=16)
    cell("f3", [0xb3, 0x8f, 0xdd, 0xf3, 0xc0, 0xff], nbytes=16)
    print("   (raw bytes above are grouped in 4; a 16-bit store gives 2 B/pass and dt 2x of A)")


if __name__ == "__main__":
    main()
