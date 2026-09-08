#!/usr/bin/env python3
"""Where do dd-routed results go? FIFO read the regmap.py way: DRAIN continuously while the
DMP runs, at the slow sample rate (SMPLRT_DIV=0xFF, FIFO divider 0 -> one packet per 256 ms,
drainable over the tunnel). Count the +1.5 pattern 60 00 00 00 in the stream.
  f1 40  control (bare emit must show hits)   dc 40  RAM (expect ~0)
  dd f1 40 / dd 40 / dc dd f1 40 / dc dd 40
Site 1866 (7 B), prefix 97 ba a4.      python3 probe16.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe4 import SlowRig
from dmpbench import USER_CTRL
SITE, SITELEN, P2 = 1866, 7, 0x240
PAT = bytes.fromhex("60000000")

class DrainRig(SlowRig):
    def emitrun(self, payload, secs=3.0):
        b = self.b
        b.mem_write(P2, bytes(4))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        buf = b""; t0 = time.time()
        while time.time() - t0 < secs:
            n = b.fifo_count()
            if n >= 32: buf += b.fifo_read(min(n, 128))
        b.wr(USER_CTRL, 0x00)
        n = b.fifo_count()
        if n: buf += b.fifo_read(min(n, 128))
        return buf, b.int_state()[1], int.from_bytes(b.mem_read(P2, 4), "big")
    def safe(self, payload):
        for _ in range(2):
            try: return self.emitrun(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def main():
    rig = DrainRig(sys.argv[1]); P = [0x97,0xBA,0xA4]
    for tag, pl in [("f1 40  (control)", P+[0xF1,0x40]), ("dc 40  (RAM)", P+[0xDC,0x40]),
                    ("dd f1 40", P+[0xDD,0xF1,0x40]), ("dd 40  (no fmode)", P+[0xDD,0x40]),
                    ("dc dd f1 40", P+[0xDC,0xDD,0xF1,0x40]), ("dc dd 40", P+[0xDC,0xDD,0x40]),
                    ("f1 40  (control again)", P+[0xF1,0x40])]:
        for _ in range(2):
            r = rig.safe(pl)
            if r is None: print(f"  {tag}: CRASH", flush=True); continue
            buf, fired, w0 = r
            print(f"  {tag:24} stream={len(buf):4}B ints={fired:3} hits={buf.count(PAT):2}  word0={w0:08x}", flush=True)

if __name__ == "__main__":
    main()
