#!/usr/bin/env python3
"""P7.5 -- MPU-6050: where the sensor samples arrive, and what bc-bf do.

Custom program at 0x300; everything else in the 3 KB tagged M[a] = 5a000000 | a.

  A  sample delivery: program `d8 f1 ff` (does nothing), T(20); every word the hardware
     overwrote.  Then field identity: all sensors on / accel standby / gyro standby
     (PWR_MGMT_2 = 0x6c), the candidate words beside the host's ACCEL/TEMP/GYRO registers
     (0x3b-0x48).
  B  bc / bd / be / bf on this core (never used by any MPU image; the DMP3 block field):
       bc b0 87 dd c0      P0 -> 0x070 + block?  the MOV emits the tag of the word it read
       bd b4 96 ...        P1 via an ADD with P0 on a zero word
       be ba a4 dc c0      P2: where does the store land?
       bf ... c0           the DMP3 MOV-zero toggle?
     Each cell under a short T with the DMP stopped afterwards; a bridge error re-initialises.

    python3 probe84.py /dev/ttyUSB0
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
PWR_MGMT_2 = 0x6C


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")
def s16(x): return x - 65536 if x & 0x8000 else x


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    b = Bridge(port)
    img = dmpinit.dmp_init(b, verbose=False)
    b.wr(SMPLRT_DIV, 0)
    TAG = {a: q32(0x5A000000 | a) for a in range(0, 0xC00, 4)}

    def tag_all():
        for a in range(0, 0xC00, 16):
            if PRGM <= a < PRGM + 0x40: continue
            b.mem_write(a, b"".join(TAG[x] for x in range(a, a + 16, 4)))

    def go(prog, ms=10):
        b.mem_write(PRGM, bytes(prog + [0xff] * 4))
        b.wr(USER_CTRL, 0x00)
        n, us = (int(x) for x in b.cmd(f"T {ms}").split())
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 32)) if fc else b""
        b.wr(USER_CTRL, 0x00)
        return [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]

    def changed(lo=0, hi=0xC00):
        mem = b.mem_read(lo, hi - lo)
        out = []
        for a in range(lo, hi, 4):
            if PRGM <= a < PRGM + 0x40: continue
            if mem[a - lo:a - lo + 4] != TAG[a]: out.append((a, int.from_bytes(mem[a - lo:a - lo + 4], "big")))
        return out

    def nm(v): return f"@{v & 0xfff:03x}" if v >> 24 == 0x5A else f"{v:x}"

    print("A. RAM words the hardware writes (program d8 f1 ff)")
    tag_all()
    go([0xd8, 0xf1], 20)
    ch = changed()
    print("   " + (" ".join(f"{a:#05x}={v:08x}" for a, v in ch) or "none"))
    words = sorted({a for a, _ in ch})
    print("   field identity (int16 halves of the changed words; host ACCEL X Y Z, TEMP, GYRO X Y Z)")
    for name, pm2 in (("all on", 0x00), ("accel standby", 0x38), ("gyro standby", 0x07)):
        b.wr(PWR_MGMT_2, pm2); time.sleep(0.05)
        print("  ", name)
        for t in range(3):
            go([0xd8, 0xf1], 20)
            m = {a: b.mem_read(a, 4) for a in words}
            h = b.rd(0x3B, 14)
            halves = " ".join(f"{a:#05x}:{s16(int.from_bytes(m[a][:2], 'big')):6d},{s16(int.from_bytes(m[a][2:], 'big')):6d}" for a in words)
            print("     ram  " + halves)
            print("     host " + " ".join(f"{s16(int.from_bytes(h[i:i+2], 'big')):6d}" for i in range(0, 14, 2)))
    b.wr(PWR_MGMT_2, 0x00)

    print("B. bc-bf on the MPU")
    b.mem_write(0x70, q32(0x11111111) * 4)
    def cell(tag, prog):
        for attempt in range(2):
            try:
                tag_all(); b.mem_write(0x70, q32(0x11111111) * 4)
                ws = go(prog, 10)
                ch = changed()
                print(f"   {tag:30s} fifo: {' '.join(nm(w) for w in ws[:4]):40s} RAM: " +
                      (" ".join(f"{a:#05x}={nm(v)}" for a, v in ch if a >= 0x14 and not (0x40 <= a < 0x70) or v in (0x11111111,)) or "no change")[:160])
                return
            except (IOError, ValueError) as e:
                print(f"   {tag:30s} bridge error ({str(e)[:40]}), re-initialising")
                time.sleep(0.5); b.__init__(port); dmpinit.dmp_init(b, verbose=False); b.wr(SMPLRT_DIV, 0)
    cell("control  b0 87 dd c0", [0xf1, 0xb0, 0x87, 0xdd, 0xc0])
    cell("bc b0 87 dd c0", [0xf1, 0xbc, 0xb0, 0x87, 0xdd, 0xc0])
    cell("bc bc b0 87 dd c0", [0xf1, 0xbc, 0xbc, 0xb0, 0x87, 0xdd, 0xc0])
    cell("b0 87 bc dd c0", [0xf1, 0xb0, 0x87, 0xbc, 0xdd, 0xc0])
    cell("control  ba a4 dc (b0 87) c0", [0xf1, 0xb0, 0x87, 0xba, 0xa4, 0xdc, 0xc0])
    cell("be ba a4 dc c0", [0xf1, 0xb0, 0x87, 0xbe, 0xba, 0xa4, 0xdc, 0xc0])
    cell("bd b4 96 dd 00 (P0 = 0x070)", [0xf1, 0xb0, 0x87, 0xbd, 0xb4, 0x96, 0xdd, 0x00])
    cell("control b4 96 dd 00", [0xf1, 0xb0, 0x87, 0xb4, 0x96, 0xdd, 0x00])
    cell("bf ba a4 dc c0", [0xf1, 0xb0, 0x87, 0xbf, 0xba, 0xa4, 0xdc, 0xc0])

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
