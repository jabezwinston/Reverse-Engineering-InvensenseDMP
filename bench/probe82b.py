#!/usr/bin/env python3
"""P7.3b -- follow-ups to probe82: which I/O words read non-zero, and where the sensor
samples actually arrive.

  A  I/O read dump, blocks 0-1: every word that reads non-zero, beside host register k = a/4
     (bank k>>7, register k&0x7f).
  B  the sensor path: tag DMP RAM 0x0000-0x0fff, run a program that does nothing (d8 f1 ff),
     and list the words the hardware overwrote.
  C  field identity: zero RAM 0x00-0x13 before each window, read it back beside the host's
     ACCEL/GYRO/TEMP registers, with all sensors on, accel in standby, gyro in standby.

    python3 probe82b.py /dev/ttyUSB1
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

SIDE = {(0, 0x19), (0, 0x1A), (0, 0x1B), (0, 0x72), (0, 0x7D)}


def s16(x): return x - 65536 if x & 0x8000 else x


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()

    print("A. non-zero I/O words (two passes each) beside host register k = a/4")
    host = {rb * 128 + r: (0 if (rb, r) in SIDE else d.rd(rb, r)[0]) for rb in range(4) for r in range(0x7F)}
    d.bank(0)
    for blk in range(2):
        for bank in range(4):
            for page in range(16):
                d.program([0xf1, 0xdd, 0xf4, 0xd8] + [0xbc] * blk + [0xb0 | bank, 0x80 | page, 0xc0, 0xc2, 0xc4, 0xc6, 0xff])
                d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 32)))[:8]
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                a = blk * 1024 + bank * 256 + page * 16
                if any(ws):
                    print(f"   {a:#06x} io " + " ".join(f"{w:08x}" for w in ws) +
                          f"   host k={a // 4:#05x}.. " + " ".join(f"{host.get(a // 4 + i, 0):02x}" for i in range(4)))

    print("B. RAM words the hardware writes (RAM tagged 5a000000|a, program d8 f1 ff)")
    tag = lambda a: q32(0x5A000000 | a)
    for a in range(0, 0x1000, 16):
        d.mem_write(a, b"".join(tag(x) for x in range(a, a + 16, 4)))
    d.program([0xd8, 0xf1, 0xff])
    d.T(50); d.wr(0, USER_CTRL, 0x40)
    mem = d.mem_read(0, 0x1000)
    for a in range(0, 0x1000, 4):
        if mem[a:a+4] != tag(a): print(f"   {a:#06x}: {mem[a:a+4].hex()}")
    print("   host accel/gyro/temp:", d.rd(0, 0x2D, 14).hex(" "))

    print("C. field identity under standby")
    for name, pm2 in (("all on", 0x00), ("accel standby", 0x38), ("gyro standby", 0x07)):
        d.wr(0, PWR_MGMT_2, pm2); time.sleep(0.05)
        print("  ", name)
        for t in range(3):
            d.mem_write(0, bytes(20)); d.T(20); d.wr(0, USER_CTRL, 0x40)
            m = d.mem_read(0, 20); hv = d.rd(0, 0x2D, 14)
            print("     ram  ax ay az gx gy gz T:", " ".join(f"{s16(int.from_bytes(m[i:i+2], 'big')):6d}" for i in range(4, 18, 2)))
            print("     host ax ay az gx gy gz T:", " ".join(f"{s16(int.from_bytes(hv[i:i+2], 'big')):6d}" for i in range(0, 14, 2)))
    d.wr(0, PWR_MGMT_2, 0x00)


if __name__ == "__main__":
    main()
