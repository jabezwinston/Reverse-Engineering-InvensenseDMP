#!/usr/bin/env python3
"""P6.4c -- mode 4 on DMP3, consolidated (the scratch cells of 2026-09-12, reproducible).

Facts established, each by the cell named:
  duration   f4 d8 [d8 d8 d8 | dd | dc dd | f8] b3 8f c0   -> 0 : d8/dc/dd/f8 do not end it
             f4 d8 [f0 | f1 | f2 | f3 | f5] b3 8f c0        -> M[0x3f0] : any f0-f7 ends it
             passes 2.. of a program that ran an f4 and never an fX read 0 (mode persists
             across passes, until DMP_RST)
  scope      bank load under mode: fine.  page load under mode: pointer -> I/O space.
             ALU / MOV with pointers loaded BEFORE the mode: normal (dead07f0 = M[3f0]+M[7f0];
             stores at 0x3e0/0x3e4).  MOV under mode is a plain MOV (f4 c2 f1 c0 -> bf4 bf0).
  doubling   x = x + x per pass with P0=P1=P2=A: 2^14 after 14 passes without f4; with an f4
             after the add the value stays 2 (pass 2 reloads pages under the mode); with the
             f4 before the add it stays 1.
  jump       f4 10 08 to a target that begins f1 -> later passes fine; to one that begins d8
             -> later passes read 0.  Hence the vendor's `d8 fX` at every one of 186 targets.
  not        indirect addressing: a pointer-valued word at 0x3f0 is read as data, not followed.

    python3 probe50.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

P, A = 0x3F0, 0x3E0


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(P, q32(0x01234567) + q32(0x89abcdef) + q32(0x0badf00d) + q32(0xdeadbeef))
    d.mem_write(0x7F0, q32(0x000007f0))

    def emit(name, prog, ms=25, n=6):
        d.program(prog); d.fifo_reset(); d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
        print(f"  {name:30s} {bytes(prog).hex():28s} -> " + " ".join(f"{w:08x}" for w in d.words(raw)[:n]))

    T = [0xdd, 0xf1, 0xc0, 0xff]
    print("duration: what ends the mode  (M[0x3f0] = 01234567; 0 = I/O space)")
    for name, mid in (("d8", [0xd8]), ("d8 d8 d8", [0xd8] * 3), ("dd", [0xdd]), ("dc dd", [0xdc, 0xdd]), ("f8", [0xf8]),
                      ("f0", [0xf0]), ("f1", [0xf1]), ("f2", [0xf2]), ("f3", [0xf3]), ("f5", [0xf5])):
        emit(f"f4 d8 {name} b3 8f", [0xf4, 0xd8] + mid + [0xb3, 0x8f] + T)
    print("persistence across passes, and f1 at a jump target")
    emit("f4 d8 ; no fX (pass 2 = 0)", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0xd8, 0xff])
    emit("f4 d8 f1 (all passes fine)", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0xd8, 0xf1, 0xff])
    emit("jump -> f1 b3 8f c4", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x10, 0x08, 0xf1, 0xb3, 0x8f, 0xc4, 0xff])
    emit("jump -> d8 b3 8f c4", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x10, 0x08, 0xd8, 0xb3, 0x8f, 0xc4, 0xff])
    print("scope: bank vs page load; pointers loaded before the mode")
    emit("f4 d8 b3 (bank only)", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0xd8, 0xb3, 0xc0, 0xff])
    emit("f4 d8 8f (page only)", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0xd8, 0x8f, 0xc0, 0xff])
    emit("add under mode, preloaded", [0xb3, 0x8f, 0xbd, 0xb7, 0x9f, 0xdd, 0xf1, 0xf4, 0xd8, 0x00, 0xff])
    emit("movs under mode, preloaded", [0xb3, 0x8f, 0xdd, 0xf1, 0xf4, 0xd8, 0xc0, 0xc2, 0xc4, 0xc6, 0xff], n=4)
    emit("f4 c2 f1 c0 (not indirect)", [0xb3, 0x8f, 0xdd, 0xf1, 0xf4, 0xc2, 0xf1, 0xc0, 0xff])
    print("doubling accumulator x = x + x, P0 = P1 = P2 = 0x3e0, ~14 passes")
    for name, prog in (("no f4", [0xb3, 0x8e, 0xb7, 0x9e, 0xbb, 0xae, 0xdc, 0xf1, 0x00, 0xff]),
                       ("f4 d8 after the add", [0xb3, 0x8e, 0xb7, 0x9e, 0xbb, 0xae, 0xdc, 0xf1, 0x00, 0xf4, 0xd8, 0xff]),
                       ("f4 d8 before the add", [0xb3, 0x8e, 0xb7, 0x9e, 0xbb, 0xae, 0xdc, 0xf1, 0xf4, 0xd8, 0x00, 0xff])):
        d.mem_write(A, q32(1)); d.program(prog); d.fifo_reset(); n, us = d.T(12); d.wr(0, USER_CTRL, 0x40)
        print(f"  {name:30s} ~{us/1e6*1136:4.1f} passes  M[A] = {int.from_bytes(d.mem_read(A, 4), 'big'):#010x}")


if __name__ == "__main__":
    main()
