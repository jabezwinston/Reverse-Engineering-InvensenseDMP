#!/usr/bin/env python3
"""P7.1 -- can a C compiler target DMP3?  The two limits the 2026-09 manual's chapter 8 left open.

  A  return-stack depth.  A chain of N routines at 0x2000 + 0x20*k; R_k calls R_k+1 and
     emits w0 after the return, the innermost emits w1, main emits w3 after its call:
         main: b3 8f dd f1  f4 60 00  f1 c6 ff
         R_k:  f4 <call R_k+1>  f1 c0 e0          R_N: f1 c2 e0
     A stack at least N deep gives  w1, (N-1) x w0, w3  =  4(N+1) B/pass.
  B  recursion.  One routine that DECs a RAM counter and calls itself while it has not gone
     negative, emitting w0 on the way down and w2 on the way up.
  C  indirect addressing.  Every DMP3 byte not yet executed (e1, e3-e6, e8-ef) is run with
     the whole data region tagged M[a] = 5a000000 | a and the P0 page holding small values
     that would be addresses if anything dereferenced them.  After the byte, MOVs emit P0's
     four words and `00` emits P0w0 + P1w0: a tag in place of a seeded value is a pointer
     that moved, and it names where to.

    python3 probe80.py /dev/ttyUSB1
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0
W = [0x11111111, 0x22222222, 0x33333333, 0x44444444]
BASE = 0x2000


def call(addr): return [0xf4, 0x40 | (addr >> 8), addr & 0xFF]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()

    def run(prog, ms=40, n=40, pre=None):
        for attempt in range(3):
            try:
                d.mem_write(0x3F0, b"".join(q32(w) for w in W))
                if pre: pre()
                d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n)) if fc else b""
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                return fc, us, d.words(raw)
            except IOError as e:
                print("     (bridge error, re-initialising:", str(e)[:40], ")")
                time.sleep(0.5); d.prepare()
        return 0, 0, []

    name = {W[0]: "w0", W[1]: "w1", W[2]: "w2", W[3]: "w3"}
    def seq(ws, k): return " ".join(name.get(w, f"{w:08x}") for w in ws[:k])

    print("A. return-stack depth: expect w1, (N-1) x w0, w3 = 4(N+1) B/pass")
    for N in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 32, 48, 64):
        for k in range(1, N + 1):
            a = BASE + 0x20 * (k - 1)
            body = (call(a + 0x20) + [0xf1, 0xc0, 0xe0]) if k < N else [0xf1, 0xc2, 0xe0]
            d.mem_write(a, bytes(body))
        fc, us, ws = run([0xb3, 0x8f, 0xdd, 0xf1] + call(BASE) + [0xf1, 0xc6, 0xff], n=N + 3)
        bpp = fc / (us / 1e6 * RATE) if us else 0
        ok = ws[:N + 1] == [W[1]] + [W[0]] * (N - 1) + [W[3]]
        print(f"   N={N:2d}  {bpp:6.2f} B/pass (expect {4*(N+1):3d})  {'OK ' if ok else 'BAD'}  {seq(ws, N + 3)}")

    print("B. recursion: R: DEC M[0x3e0]; if >= 0 { emit w0; call R; emit w2 }; ret")
    # main: P0 -> 0x3f0 (the emit words), P2 -> 0x3e0 (the counter, RAM-routed for DEC)
    #   R  = 0x2800:  f1 dc b3 8e ae? -- keep P0 on 0x3f0; P2 = bank3 page e = 0x3e0
    #        d8 dc f9          DEC M[0x3e0] under d8 so F is live;  F = (count < 0)
    #        da f4 <body>      not negative -> body;   else  d8 f1 e0
    R = 0x2800
    body = R + 12
    r = [0xf1, 0xbb, 0xae, 0xd8, 0xdc, 0xf9, 0xda, 0xf4, body >> 8, body & 0xFF, 0xd8, 0xe0]
    #    body: d8 f1 dd c0 (emit w0)  call R  f1 dd c4 (emit w2)  e0
    r += [0xd8, 0xf1, 0xdd, 0xc0] + call(R) + [0xf1, 0xdd, 0xc4, 0xe0]
    d.mem_write(R, bytes(r))
    # main reloads the counter every pass: M[0x3e0] := M[0x3d0] = n (RAM-routed MOV)
    main_ = [0xf1, 0xb3, 0x8d, 0xbb, 0xae, 0xdc, 0xc0, 0xb3, 0x8f] + call(R) + [0xf1, 0xdd, 0xc6, 0xff]
    for n in (0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32):
        fc, us, ws = run(main_, n=2 * n + 3, pre=lambda n=n: d.mem_write(0x3D0, q32(n) + bytes(12)))
        bpp = fc / (us / 1e6 * RATE) if us else 0
        exp = [W[0]] * n + [W[2]] * n + [W[3]]
        ok = ws[:len(exp)] == exp
        print(f"   depth {n:2d}  {bpp:6.2f} B/pass (expect {4*(2*n+1):3d})  {'OK ' if ok else 'BAD'}  {seq(ws, 2*n+3)}")

    print("C. indirect-addressing screen: tag the data region, seed P0's page with small values")
    print("   tagging 0x0000-0x0fff ...", flush=True)
    for a in range(0, 0x1000, 16):
        d.mem_write(a, b"".join(q32(0x5A000000 | x) for x in range(a, a + 16, 4)))
    SEED = [0x00000005, 0x00000123, 0x00000200, 0x000003e0]
    # P0 -> 0x3f0 (seeded), P1 -> 0x3e0 (tagged), FIFO route; X then padding d8 x3 so a byte
    # that swallows operands swallows d8s; then emit P0 w0..w3 and P0w0 + P1w0.
    PRE = [0xb3, 0x8f, 0xb7, 0x9e, 0xdd, 0xf1]
    POST = [0xd8, 0xd8, 0xd8, 0xf1, 0xc0, 0xc2, 0xc4, 0xc6, 0x00, 0xff]

    def seed_pages():
        d.mem_write(0x3F0, b"".join(q32(w) for w in SEED))
        d.mem_write(0x3E0, b"".join(q32(0x5A000000 | x) for x in range(0x3E0, 0x3F0, 4)))

    def desc(w):
        if w in SEED: return f"s{SEED.index(w)}"
        if w >> 24 == 0x5A: return f"@{w & 0xffffff:03x}"
        return f"{w:08x}"

    W[:] = SEED      # run() re-seeds 0x3f0 with W
    for x in [None, 0xe1, 0xe3, 0xe4, 0xe5, 0xe6] + list(range(0xe8, 0xf0)):
        prog = PRE + ([] if x is None else [x]) + POST
        fc, us, ws = run(prog, n=12, pre=seed_pages)
        bpp = fc / (us / 1e6 * RATE) if us else 0
        tag = "ctrl" if x is None else f"{x:02x}"
        print(f"   {tag:4s} {bpp:6.2f} B/pass  " + " ".join(desc(w) for w in ws[:10]))
    print("   control expectation: s0 s1 s2 s3, then s0 + @3e0 = 5a0003e5")


if __name__ == "__main__":
    main()
