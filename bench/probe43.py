#!/usr/bin/env python3
"""Does the stock DMP3 image run on the bench ICM-20948?

Vendor sequence (SparkFun initializeDMP minus the magnetometer): reset, sensors at 55 Hz,
PRGM_START = 0x1000, image at 0x90 with verify, HW_FIX_DISABLE/FIFO priority, then the DMP
output-control words asking for 16-bit accel every sample.  Success = FIFO fills with
DMP3 packets (header 0x8000, 6 B accel, 2 B footer = 10 B) and INT1 edges accumulate.

Trap found on the way: with USER_CTRL.FIFO_EN cleared the ICM disables serial access to
the FIFO and FIFO_R_W returns one stuck byte (0x80 or 0xe7 here) without decrementing the
count.  Stopping the DMP must leave FIFO_EN set (icm.ICM.dmp_stop writes 0x40, not 0x00).

Three observations, each independent of the others:
  A. FIFO count and INT count over a 2 s window with the DMP running.
  B. First packets from the FIFO, decoded.
  C. The bridge's T single-step: does one DMP_INT1 arrive, and how long after start?

    python3 probe43.py rfc2217://localhost:5555
"""
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *


def main():
    d = ICM(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.reset()
    d.sensors(gyro_div=19, accel_div=19)
    d.set_entry()
    n = d.load()
    d.set_entry()
    d.post_load()
    print(f"loaded {n} B at {LOAD_ADDR:#06x}, verified; entry {ENTRY:#06x}")
    d.dmp_output(OUT_ACCEL)
    d.int_config()

    print("A. run 2 s")
    d.b.cmd("Z")
    d.dmp_start()
    t0 = time.time(); time.sleep(2.0)
    fc = d.fifo_count(); lvl, ints = d.int_state(); dt = time.time() - t0
    st = d.int_status()
    d.dmp_stop()
    print(f"   FIFO count {fc}  INT edges {ints} in {dt:.2f} s ({ints/dt:.1f}/s)  INT_STATUS {st.hex()}")

    print("B. first packets")
    d.fifo_reset(); d.b.cmd("Z")
    d.dmp_start(); time.sleep(0.3); d.dmp_stop()
    fc = d.fifo_count()
    raw = d.fifo_read(min(fc, 60)) if fc else b""
    print(f"   FIFO count {fc}; first {len(raw)} B: {raw.hex()}")
    i = 0
    while i + 10 <= len(raw) and i < 40:
        hdr = int.from_bytes(raw[i:i+2], "big")
        if hdr == 0x8000:
            ax, ay, az = (int.from_bytes(raw[i+2+2*k:i+4+2*k], "big", signed=True) for k in range(3))
            print(f"   pkt hdr {hdr:#06x} accel {ax:6d} {ay:6d} {az:6d} footer {raw[i+8:i+10].hex()}")
            i += 10
        else:
            print(f"   at {i}: header {hdr:#06x} (unexpected)"); break

    print("C. single step (T 1500) x3")
    for _ in range(3):
        n, us = d.T(1500)
        print(f"   ints={n} dt={us} us")
    d.dmp_stop()


if __name__ == "__main__":
    main()
