#!/usr/bin/env python3
"""P4.x2 -- run the 2639-byte image (the one with the validated 138-entry symbol table) on the
MPU-6050.  Same mantis ISA; the image loads identity-mapped and its program start is 0x0400
(REG_PRGM_STRT_ADDRH=0x70 <- 0x04,0x00; the kernel hammerhead driver).  The 1929 image the bench
has always used starts at 0x0300.  This confirms the 2639 image executes on silicon and validates
its symbol addresses (D_FS_Q0 = unit quaternion at 0xC0).

    python3 probe78.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit as D

IMAGE = "../corpus/images/f80d502b66daab2f_2639.bin"


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = pathlib.Path(IMAGE).read_bytes()
    # --- init, 2639-image variant of dmpinit.dmp_init ---
    b.wr(D.PWR_MGMT_1, 0x80); time.sleep(0.1)
    b.wr(D.PWR_MGMT_1, 0x00)
    b.wr(D.PWR_MGMT_1, 0x03)                 # clock = PLL / Z gyro
    b.wr(D.GYRO_CONFIG, 0x18)                # +-2000 dps
    b.wr(D.ACCEL_CONFIG, 0x00)               # +-2 g
    b.wr(D.CONFIG, 0x03); b.wr(0x1D, 0x03)   # DLPF
    b.wr(D.SMPLRT_DIV, 4)
    b.wr(D.INT_ENABLE, 0x00)
    b.wr(USER_CTRL, 0x04); time.sleep(0.05)  # FIFO reset
    # load the image identity-mapped
    b.mem_write(0, img)
    back = b.mem_read(0, len(img))
    bad = sum(1 for i in range(len(img)) if back[i] != img[i])
    print(f"2639 image loaded at 0x000, verify: {len(img)-bad}/{len(img)} bytes match")
    # validate symbol addresses against loaded content
    def w(a): return int.from_bytes(b.mem_read(a, 4), "big")
    print(f"  D_FS_Q0..Q3 (0x0C0): " + " ".join(f"{w(0xC0+4*i):08x}" for i in range(4)) + "   (symbol table: unit quaternion)")
    # program start 0x0400
    b.wr(0x70, 0x04); b.wr(0x71, 0x00)
    b.wr(USER_CTRL, 0x08); time.sleep(0.05)  # DMP reset
    b.wr(USER_CTRL, 0xC8)                    # DMP_EN | FIFO_EN | FIFO_RESET
    b.wr(USER_CTRL, 0xC0)
    b.wr(D.INT_ENABLE, 0x02)                 # DMP_INT
    print("\nrunning (start 0x0400); T single-steps to the first interrupt:")
    for rep in range(4):
        b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)   # FIFO reset
        n, us = (int(x) for x in b.cmd("T 300").split())
        fc = b.fifo_count()
        raw = b.fifo_read(min(fc, 64))
        ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw)-3, 4)]
        print(f"  rep {rep}: ints={n} dt={us:6d}us fifo={fc:3d}B  " + " ".join(f"{x:08x}" for x in ws[:8]))
        time.sleep(0.05)
    print("\n(a repeating packet with a ~40000000 leading word at rest = the image runs and emits a quaternion)")
    # restore: reload the 1929 image and its start so the bench default is back
    b.wr(USER_CTRL, 0x00)
    b.mem_write(0, pathlib.Path("../corpus/images/d79e55736bb5ea91_1929.bin").read_bytes())
    b.wr(0x70, 0x03); b.wr(0x71, 0x00)
    print("restored the 1929 image and start 0x0300")


if __name__ == "__main__":
    main()
