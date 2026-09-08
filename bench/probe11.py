#!/usr/bin/env python3
"""Identify the predicate conditions. probe10 showed d8 always stores, d9/db store (cond
TRUE in idle), da suppresses the next instruction (cond FALSE in idle, sensors in standby).

Flip machine state and re-test each prefix with the store idiom as detector:
  state A  sensors standby (PWR_MGMT_2=0x3F)      -- probe10 baseline
  state B  all sensors on   (PWR_MGMT_2=0x00)
  state C  gyro on, accel off (0x38)
  state D  accel on, gyro off (0x07)
A prefix whose store flips between states has a sensor-dependent condition; the pattern of
which states enable it names the flag.  Placement: before-alu  [97 ba a4 dc pre 40].
    python3 probe11.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL

SITE, SITELEN, P2, PWR2 = 1867, 6, 0x240, 0x6C
IDIOM = [0x97, 0xBA, 0xA4, 0xDC, 0x40]
STATES = {"standby 3F": 0x3F, "all-on 00": 0x00, "gyro-only 38": 0x38, "accel-only 07": 0x07}

class R(Rig):
    def run(self, payload):
        b = self.b
        b.mem_write(P2, bytes(4))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        return int.from_bytes(b.mem_read(P2, 4), "big")
    def safe(self, payload):
        for _ in range(2):
            try: return self.run(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def cell(v): return "CRASH" if v is None else ("store" if v == 0x60000000 else f"{v:08x}")

def main():
    rig = R(sys.argv[1])
    pres = (0xD8, 0xD9, 0xDA, 0xDB)
    print(f"{'state':16}" + "".join(f"{p:02x}{'':>12}" for p in pres) + "  (before-alu placement, x2)")
    for name, pwr in STATES.items():
        rig.b.wr(PWR2, pwr); time.sleep(0.3)
        row = []
        for p in pres:
            vals = [rig.safe(IDIOM[:4] + [p] + IDIOM[4:]) for _ in range(2)]
            row.append(f"{cell(vals[0])}/{cell(vals[1])}")
        print(f"{name:16}" + "".join(f"{r:<14}" for r in row), flush=True)
    rig.b.wr(PWR2, 0x3F)

if __name__ == "__main__":
    main()
