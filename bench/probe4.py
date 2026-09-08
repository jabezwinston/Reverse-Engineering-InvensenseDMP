#!/usr/bin/env python3
"""Latency-proof single step + "which byte stores?" sweep.

Over the RFC2217 tunnel each bridge command costs ~100 ms, so the round-18 stepper (start,
poll INT, stop) lets the DMP run ~64 samples per "step". Fix: slow the sensor sample rate to
1 kHz/256 = 3.9 Hz and set the FIFO-rate divider to 0, so one DMP execution = one packet =
one interrupt every 256 ms, then accept a step only if exactly one interrupt fired.

Detector: P2 aimed at 0x240 (bank 2, page 4), an all-zero page nothing in the 1929 program
touches. Any non-zero word there after a step is a store.

Sweep: payload `ba a4 30 X` for X in 0x80..0xff (5-byte site 1868, `a3`-padded).  A control
`ba a4 30` is re-measured every 8 candidates.

    python3 probe4.py rfc2217://localhost:5555 [lo hi]
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, word, q, SITE, SITELEN, RAM
from dmpbench import USER_CTRL

SMPLRT_DIV = 0x19
PAGE = 0x240


class SlowRig(Rig):
    def reinit(self):
        super().reinit()
        self.b.wr(SMPLRT_DIV, 0xFF)                 # 1 kHz / 256 = 3.9 Hz sample rate
        self.b.mem_write(0x0216, bytes([0x00, 0x00]))  # FIFO-rate divider 0: packet every sample
        time.sleep(0.1)

    has_T = None

    def step(self, payload, want=1, tries=4):
        """Run until exactly `want` interrupts fired; returns (ram, fired, fifo).
        Uses the bridge's hardware step command `T` when the flashed sketch has it."""
        b = self.b
        payload = bytes(payload)
        b.mem_write(SITE, payload + b"\xa3" * (SITELEN - len(payload)))
        if SlowRig.has_T is None:
            try:
                r = b.cmd("T 600"); SlowRig.has_T = True
                print("bridge has hardware step (T):", r, flush=True)
            except IOError:
                SlowRig.has_T = False
                print("bridge lacks T; using slow-rate host stepping", flush=True)
        if SlowRig.has_T:
            for _ in range(tries):
                n, us = b.cmd("T 600").split()
                if int(n) == want:
                    return b.mem_read(0, RAM), int(n), b.fifo_count()
            return b.mem_read(0, RAM), int(n), b.fifo_count()
        for _ in range(tries):
            b.wr(USER_CTRL, 0x00)
            b.cmd("Z")
            b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
            fired = 0
            t0 = time.time()
            while time.time() - t0 < 1.2:
                fired = b.int_state()[1]
                if fired >= want:
                    break
            b.wr(USER_CTRL, 0x00)
            fired = b.int_state()[1]
            if fired == want:
                return b.mem_read(0, RAM), fired, b.fifo_count()
        return b.mem_read(0, RAM), fired, b.fifo_count()


def pagewords(s, base=PAGE, n=4):
    return [word(s, base + 4 * i) for i in range(n)]


def main():
    port = sys.argv[1]
    lo = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x80
    hi = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x100
    rig = SlowRig(port)
    # calibrate the stepper
    for i in range(3):
        s, fired, fifo = rig.safe([0xA3])
        print(f"calibration step {i}: int={fired} fifo={fifo}", flush=True)
    s, _, _ = rig.safe([0xA3])
    print("control 0x240:", [f"{w:08x}" for w in pagewords(s)], " 0x250:", [f"{w:08x}" for w in pagewords(s, 0x250)],
          " P1 0xd0:", [f"{w:08x}" for w in pagewords(s, 0xd0)], flush=True)
    hits = []
    for k, x in enumerate(range(lo, hi)):
        if k % 8 == 0:
            s, fired, _ = rig.safe([0xBA, 0xA4, 0x30])
            pw = pagewords(s) if s is not None else None
            print(f"  control ba a4 30 : int={fired} 0x240={[f'{w:08x}' for w in pw] if pw else 'CRASH'}", flush=True)
        s, fired, fifo = rig.safe([0xBA, 0xA4, 0x30, x])
        if s is None:
            print(f"{x:02x}: CRASH", flush=True); continue
        pw = pagewords(s); pw2 = pagewords(s, 0x250)
        nz = [(PAGE + 4 * i, w) for i, w in enumerate(pw) if w] + [(0x250 + 4 * i, w) for i, w in enumerate(pw2) if w]
        tag = "  <== STORE " + " ".join(f"{a:#x}={w:08x}({q(w):+.4f})" for a, w in nz) if nz else ""
        print(f"{x:02x}: int={fired} fifo={fifo}{tag}", flush=True)
        if nz:
            hits.append((x, nz))
            # scrub the page so the next candidate starts clean
            rig.b.mem_write(PAGE, bytes(32))
    print("\nSTORE candidates:", [f"{x:02x}" for x, _ in hits])


if __name__ == "__main__":
    main()
