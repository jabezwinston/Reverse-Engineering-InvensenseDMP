#!/usr/bin/env python3
"""P7.6 -- the 2639 image's FIFO output, enabled the way the hammerhead kernel driver does it.

Driver (corpus/sources_kernel/hammerhead-lmr1__inv_mpu_ring.c, inv_send_*_data): each output
slot CFG_OUT_x holds `f4 12` (skip the emit block) when off and is overwritten with `a3 a3`
to turn it on; the rate is D_ODR_Sx = 200/rate - 1 with its counter D_ODR_CNTR_Sx zeroed;
KEY_CFG_FIFO_INT is `fe` (DMP_INT every pass) or `a3` (gesture-only).  Keys from
hammerhead-lmr1__dmpDefaultMPU6050.c; every CFG_OUT slot in the image reads `f4 12`/`f4 13`.

Prediction from the decode of the accel block at 2166 (`dd f3 b1 87 b5 9a 68 f2 b0 80 c0 c8
c2 dc f3 b9 ac f8`): per sample, a 2-byte header (the `68` ALU store under f3) then the upper
half of RAM 0x000, the swapped word 0x000 (its lower half) and the upper half of 0x004 --
accel X, Y, Z exactly as the hardware wrote them (Finding 35).  Gyro: `c4 cc c6` = RAM
0x008/0x00c, gyro X, Y, Z.  The 6-axis quaternion: `f1 b0 88 c2 c4 c6`, three 32-bit words
of page 0x080, after two 16-bit header halves.

Gate: the pass halts at 1049 (`31 d1 da f1 ff`) unless the half-word at 0x16a (D_1_106, image
default 3) is 0; nothing on the 6050 clears it and the driver never writes it.  Cells are run
with it cleared (`gate`), and once as shipped.

    python3 probe85.py /dev/ttyUSB0
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL
import dmpinit as D

IMAGE = pathlib.Path(__file__).resolve().parent.parent / "corpus/images/f80d502b66daab2f_2639.bin"
STOCK = pathlib.Path(__file__).resolve().parent.parent / "corpus/images/d79e55736bb5ea91_1929.bin"
INT_ENABLE = 0x38
OUT = {"accel": (2164, 46 * 16 + 8, 46 * 16), "gyro": (2198, 46 * 16 + 12, 46 * 16 + 4),
       "quat6": (2095, 45 * 16 + 10, 45 * 16 + 2)}
CFG_FIFO_INT, D_DMP_RUN_CNTR = 2362, 24 * 16


def s16(b, i): v = (b[i] << 8) | b[i + 1]; return v - 65536 if v & 0x8000 else v
def s32(b, i): v = int.from_bytes(b[i:i+4], "big"); return v - (1 << 32) if v & 0x80000000 else v


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0")
    img = IMAGE.read_bytes()
    b.wr(D.PWR_MGMT_1, 0x80); time.sleep(0.1); b.wr(D.PWR_MGMT_1, 0x03)
    b.wr(D.GYRO_CONFIG, 0x18); b.wr(D.ACCEL_CONFIG, 0x00)
    b.wr(D.CONFIG, 0x03); b.wr(D.SMPLRT_DIV, 4)                  # 200 Hz = MPU_DEFAULT_DMP_FREQ
    b.wr(INT_ENABLE, 0x02)                                      # DMP_INT only

    def load(outputs, fifo_int=0xFE, gate=True):
        b.wr(USER_CTRL, 0x00)
        b.mem_write(0, img)
        b.wr(0x70, 0x04); b.wr(0x71, 0x00)
        for o in outputs:
            slot, odr, cntr = OUT[o]
            b.mem_write(slot, b"\xa3\xa3")
            b.mem_write(odr, b"\x00\x00"); b.mem_write(cntr, b"\x00\x00")
        b.mem_write(CFG_FIFO_INT, bytes([fifo_int]))
        b.mem_write(D_DMP_RUN_CNTR, bytes(4))
        if gate: b.mem_write(0x16A, b"\x00\x00")

    def run(ms=200):
        _, c0 = b.cmd("I").split()
        b.wr(USER_CTRL, 0x04); b.wr(USER_CTRL, 0x08); time.sleep(0.005)     # FIFO reset, DMP reset
        b.wr(USER_CTRL, 0xC0); time.sleep(ms / 1000)                       # DMP + FIFO
        b.wr(USER_CTRL, 0x40)
        _, c1 = b.cmd("I").split()
        host = b.rd(0x3B, 14)
        fc = b.fifo_count(); raw = b""
        while len(raw) < min(fc, 96):
            raw += b.fifo_read(min(128, min(fc, 96) - len(raw)))
        return int(c1) - int(c0), fc, raw, host

    cells = [("accel, as shipped (gate closed)", ["accel"], 0xFE, False), ("none", [], 0xFE), ("accel", ["accel"], 0xFE), ("gyro", ["gyro"], 0xFE),
             ("accel+gyro", ["accel", "gyro"], 0xFE), ("quat6", ["quat6"], 0xFE),
             ("accel, FIFO_INT = a3", ["accel"], 0xA3)]
    for cell in cells:
        name, outs, fi = cell[:3]
        load(outs, fi, cell[3] if len(cell) > 3 else True)
        ints, fc, raw, host = run(200)
        print(f"{name}: {ints} DMP_INT edges in 200 ms, FIFO {fc} B" + (f" = {fc / max(ints, 1):.1f} B/interrupt" if ints else ""))
        print("   host accel " + " ".join(str(s16(host, i)) for i in (0, 2, 4)) + "   gyro " + " ".join(str(s16(host, i)) for i in (8, 10, 12)))
        for k in range(0, min(len(raw), 48), 16):
            print("   fifo " + raw[k:k+16].hex(" "))
        if name == "accel" and len(raw) >= 24:
            for p in range(3):
                q = raw[8 * p:8 * p + 8]
                print(f"   packet {p}: header {q[:2].hex()}  accel {s16(q, 2)} {s16(q, 4)} {s16(q, 6)}")
        if name == "gyro" and len(raw) >= 24:
            for p in range(3):
                q = raw[8 * p:8 * p + 8]
                print(f"   packet {p}: header {q[:2].hex()}  gyro {s16(q, 2)} {s16(q, 4)} {s16(q, 6)}")
        if name == "quat6" and len(raw) >= 48:
            for p in range(3):
                q = raw[16 * p:16 * p + 16]
                x, y, z = (s32(q, 4 + 4 * i) / 2**30 for i in range(3))
                print(f"   packet {p}: header {q[:4].hex()}  q x y z = {x:+.6f} {y:+.6f} {z:+.6f}")

    b.wr(USER_CTRL, 0x00)
    b.mem_write(0, STOCK.read_bytes()); b.wr(0x70, 0x03); b.wr(0x71, 0x00)
    print("restored the 1929 image and start 0x0300")


if __name__ == "__main__":
    main()
