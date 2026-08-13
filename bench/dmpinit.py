#!/usr/bin/env python3
"""Faithful MotionApps20 dmpInitialize(), ported from i2cdevlib.

The earlier minimal init produced a valid quaternion but left the part in a
non-standard configuration: clock on PLL/X-gyro instead of Z-gyro, no external
frame sync, no FIFO-rate patch, and DMP_CFG_1 set to 0x04 (the MotionApps612
program-start convention) rather than 0x03. Config data below PRGM_START was
therefore never consumed the way the firmware expects.

Import `dmp_init` and call it instead of quat_probe.init.
"""
import time

# registers
XG_OFFS_TC   = 0x00
SMPLRT_DIV   = 0x19
CONFIG       = 0x1A
GYRO_CONFIG  = 0x1B
ACCEL_CONFIG = 0x1C
MOT_THR      = 0x1F
MOT_DUR      = 0x20
ZRMOT_THR    = 0x21
ZRMOT_DUR    = 0x22
INT_ENABLE   = 0x38
I2C_SLV0_ADDR= 0x25
USER_CTRL    = 0x6A
PWR_MGMT_1   = 0x6B
DMP_CFG_1    = 0x70
DMP_CFG_2    = 0x71

FIFO_RATE_DIVISOR = 0x01
IMAGE = "../corpus/images/d79e55736bb5ea91_1929.bin"


def dmp_init(b, image=IMAGE, verbose=True):
    img = open(image, "rb").read()

    b.wr(PWR_MGMT_1, 0x80)                  # device reset
    time.sleep(0.1)
    b.wr(PWR_MGMT_1, 0x00)                  # wake, clear sleep
    time.sleep(0.02)

    b.wr(I2C_SLV0_ADDR, 0x7F)               # slave 0 -> 0x7F
    b.wr(USER_CTRL, 0x00)                   # disable I2C master
    b.wr(I2C_SLV0_ADDR, 0x68)               # slave 0 -> self
    b.wr(USER_CTRL, 0x02)                   # reset I2C master
    time.sleep(0.02)

    b.wr(PWR_MGMT_1, 0x03)                  # clock = PLL / Z gyro
    b.wr(INT_ENABLE, (1 << 4) | (1 << 1))   # FIFO_OFLOW | DMP_INT
    b.wr(SMPLRT_DIV, 4)                     # 1 kHz / (1+4) = 200 Hz
    b.wr(CONFIG, (1 << 3) | 3)              # EXT_SYNC=TEMP_OUT_L, DLPF=42 Hz
    b.wr(GYRO_CONFIG, 0x18)                 # +/- 2000 dps
    b.wr(ACCEL_CONFIG, 0x00)

    b.mem_write(0, img)                     # load firmware
    back = b.mem_read(0, len(img))
    if back != img:
        raise RuntimeError("firmware verify failed")

    # FIFO-rate patch: 2 bytes at bank 0x02, offset 0x16  ->  address 0x216
    b.mem_write(0x0216, bytes([0x00, FIFO_RATE_DIVISOR]))

    b.wr(DMP_CFG_1, 0x03)                   # NOT 0x04 - that is MotionApps612
    b.wr(DMP_CFG_2, 0x00)

    otp = b.rd(XG_OFFS_TC, 1)[0]
    b.wr(XG_OFFS_TC, otp & ~0x01)           # clear OTP bank valid

    b.wr(MOT_THR, 2)
    b.wr(ZRMOT_THR, 156)
    b.wr(MOT_DUR, 80)
    b.wr(ZRMOT_DUR, 0)

    b.wr(USER_CTRL, 0x40)                   # FIFO enable
    b.wr(USER_CTRL, 0x48)                   # + DMP reset
    time.sleep(0.05)
    b.wr(USER_CTRL, 0x40)
    if verbose:
        print(f"dmpInitialize: {len(img)} B loaded and verified, "
              f"DMP_CFG_1=0x03, clock=PLL/Zgyro, FIFO rate div={FIFO_RATE_DIVISOR}")
    return img


def dmp_go(b):
    b.wr(USER_CTRL, 0x4C)                   # FIFO_EN | FIFO_RESET | DMP_RESET
    time.sleep(0.05)
    b.wr(USER_CTRL, 0xC0)                   # DMP_EN | FIFO_EN


def dmp_halt(b):
    b.wr(USER_CTRL, 0x00)
