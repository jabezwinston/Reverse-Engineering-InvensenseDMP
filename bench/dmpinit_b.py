#!/usr/bin/env python3
"""Family B bring-up (ml_load_dmp.c images, 2634-3065 B), per the inv_mpu kernel driver.

Differs from MotionApps20 in three ways that matter:

  * MPU_DMP_LOAD_START = 0x20 - the first 32 bytes of the image are NOT written;
    loading starts at DMP address 0x20 from image offset 0x20.
  * The program start address IS register 0x70/0x71, set to DMP_START_ADDR = 0x400.
    (For MotionApps20 register 0x70 is DMP_CFG_1 = 0x03 instead.)
  * Outputs are disabled in the shipped image and must be enabled by writing
    register references into the CFG_OUT_* config points.
"""
import time

SMPLRT_DIV, CONFIG, GYRO_CONFIG, ACCEL_CONFIG = 0x19, 0x1A, 0x1B, 0x1C
INT_ENABLE, USER_CTRL, PWR_MGMT_1 = 0x38, 0x6A, 0x6B
PRGM_STRT_ADDRH = 0x70

MPU_DMP_LOAD_START = 0x20
MPU_MEM_BANK_SIZE = 256
DMP_START_ADDR = 0x400


def load_firmware(b, img):
    """Mirror inv_load_firmware(): skip the first 0x20 bytes of the image."""
    b.mem_write(MPU_DMP_LOAD_START, img[MPU_DMP_LOAD_START:])
    back = b.mem_read(MPU_DMP_LOAD_START, len(img) - MPU_DMP_LOAD_START)
    bad = sum(1 for i in range(len(back)) if back[i] != img[MPU_DMP_LOAD_START + i])
    return len(back), bad


def init_b(b, path, verbose=True):
    img = open(path, "rb").read()

    b.wr(PWR_MGMT_1, 0x80); time.sleep(0.1)
    b.wr(PWR_MGMT_1, 0x00); time.sleep(0.02)
    b.wr(USER_CTRL, 0x00)
    b.wr(PWR_MGMT_1, 0x03)                    # PLL / Z gyro
    b.wr(SMPLRT_DIV, 4)
    b.wr(CONFIG, 0x03)                        # DLPF 42 Hz
    b.wr(GYRO_CONFIG, 0x18)                   # +/- 2000 dps
    b.wr(ACCEL_CONFIG, 0x00)
    b.wr(INT_ENABLE, 0x00)

    n, bad = load_firmware(b, img)
    if verbose:
        print(f"loaded {path.split('/')[-1]} ({len(img)} B): wrote {n} bytes from "
              f"offset 0x{MPU_DMP_LOAD_START:02x}, verify mismatches = {bad}")
    if bad:
        raise RuntimeError(f"firmware verify failed ({bad} bytes)")

    b.wr(PRGM_STRT_ADDRH, bytes([DMP_START_ADDR >> 8, DMP_START_ADDR & 0xFF]))
    b.wr(INT_ENABLE, 0x02)                    # DMP interrupt
    b.wr(USER_CTRL, 0x40)                     # FIFO enable
    if verbose:
        print(f"prog start = 0x{DMP_START_ADDR:04x} written to reg 0x70/0x71")
    return img


def go(b):
    b.wr(USER_CTRL, 0x4C)                     # FIFO_EN | FIFO_RESET | DMP_RESET
    time.sleep(0.05)
    b.wr(USER_CTRL, 0xC0)                     # DMP_EN | FIFO_EN


def halt(b):
    b.wr(USER_CTRL, 0x00)
