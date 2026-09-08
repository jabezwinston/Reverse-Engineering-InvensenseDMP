# 5. Host interface

The DMP has no independent existence: the host loads its program, starts it, and reads its
output. Everything in this chapter is MPU-6050 over I²C at address 0x68, measured on the bench
rig **[HW]** unless tagged otherwise.

## 5.1 Registers you need

| reg | name | use |
|---|---|---|
| `0x19` | `SMPLRT_DIV` | sample rate = 1 kHz / (1 + div). The DMP program runs once per sample |
| `0x1A` | `CONFIG` | external sync + DLPF |
| `0x1B` / `0x1C` | `GYRO_CONFIG` / `ACCEL_CONFIG` | full-scale ranges |
| `0x38` | `INT_ENABLE` | bit 1 `DMP_INT`, bit 4 `FIFO_OFLOW` |
| `0x6A` | `USER_CTRL` | FIFO enable, DMP enable, and the two resets |
| `0x6B` | `PWR_MGMT_1` | device reset, sleep, clock source |
| `0x6D` | `BANK_SEL` | DMP memory bank (0–15 for 4 KB; masked to 5 bits) |
| `0x6E` | `MEM_START_ADDR` | offset within the bank |
| `0x6F` | `MEM_R_W` | the DMP memory data port — burst reads and writes |
| `0x70` / `0x71` | `DMP_CFG_1` / `DMP_CFG_2` | **the program entry point**, big-endian |
| `0x72` / `0x73` | `FIFO_COUNT_H/L` | bytes available |
| `0x74` | `FIFO_R_W` | FIFO data port |
| `0x75` | `WHO_AM_I` | reads 0x68 |

## 5.2 Reading and writing DMP memory

```
    write BANK_SEL      = address >> 8
    write MEM_START_ADDR= address & 0xff
    burst read/write MEM_R_W        -- the address auto-increments within the bank
```

A burst must not cross a bank boundary; split it. This is the whole oracle the ISA recovery rests
on — if you can write DMP RAM and read it back, you can run an instruction and observe it.

## 5.3 Loading and starting a program

The sequence below is the i2cdevlib `dmpInitialize()` for MotionApps20, which is what the bench
uses (`bench/dmpinit.py`). It matters that it is faithful: an earlier minimal init produced a
plausible quaternion while leaving the clock on the X gyro and `DMP_CFG_1` at the MotionApps612
value, so the configuration data below the entry point was never consumed the way the firmware
expects.

```python
    wr(PWR_MGMT_1, 0x80); sleep(0.1)        # device reset
    wr(PWR_MGMT_1, 0x00)                    # wake

    wr(I2C_SLV0_ADDR, 0x7F); wr(USER_CTRL, 0x00)    # disable the I2C master
    wr(I2C_SLV0_ADDR, 0x68); wr(USER_CTRL, 0x02)    # reset it

    wr(PWR_MGMT_1, 0x03)                    # clock = PLL / Z gyro
    wr(INT_ENABLE, (1<<4) | (1<<1))         # FIFO_OFLOW | DMP_INT
    wr(SMPLRT_DIV, 4)                       # 1 kHz / 5 = 200 Hz
    wr(CONFIG, (1<<3) | 3)                  # EXT_SYNC = TEMP_OUT_L, DLPF 42 Hz
    wr(GYRO_CONFIG, 0x18)                   # +/- 2000 dps
    wr(ACCEL_CONFIG, 0x00)

    mem_write(0, image)                     # load, then read back and compare
    mem_write(0x0216, bytes([0x00, div]))   # the FIFO-rate divider, 2 bytes at bank 2 + 0x16

    wr(DMP_CFG_1, 0x03); wr(DMP_CFG_2, 0x00)        # entry point 0x0300 for Family A
    wr(XG_OFFS_TC, otp & ~0x01)                     # clear "OTP bank valid"

    wr(USER_CTRL, 0x40)                     # FIFO enable
    wr(USER_CTRL, 0x48); sleep(0.05)        # + DMP reset
    wr(USER_CTRL, 0x40)
```

Then run, and stop:

```python
    def go():   wr(USER_CTRL, 0x4C); sleep(0.05); wr(USER_CTRL, 0xC0)   # reset, then DMP_EN|FIFO_EN
    def halt(): wr(USER_CTRL, 0x00)
```

**Always verify the load by reading it back.** A silent I²C failure produces a clean-looking
null result, which has cost this project three false conclusions.

The entry point is `0x0300` for Family A images (1024, 1923, 1929, 1962) and `0x0400` for
Family B — see [chapter 1 §1.7](01-machine-model.md#17-image-layout).

## 5.4 The output FIFO

The DMP writes packets into the FIFO; the host drains them through `FIFO_R_W`. There is no packet
header — you find the boundaries by the **2-byte footer**, `b2 6a` for MotionApps20, and by the
fact that the packet length is fixed by the program.

Stock MotionApps20 (1929-byte image), measured:

| bytes | content | emitted at |
|---|---|---|
| 16 | quaternion w, x, y, z (Q30) | 1858–1861 |
| 12 | gyro x, y, z | 1864–1866 |
| 12 | accel x, y, z | 1901–1903 |
| 2 | footer `b2 6a` | 1918 |
| **42** | **total** | |

Each 32-bit emit adds 4 bytes and each 16-bit emit adds 2, so **the packet length is a prediction
you can make before the run** — which is exactly how a custom program is verified (§5.6).

> The RAM symbol names in the listings come from `dmpmap.h`, which is written for the 1923-byte
> `dmpDefaultMantis.c` image. They are approximate for other images: the third emit group in the
> 1929-byte image decodes under `dmpmap.h` names that are not "accel", yet the emitted words
> cross-check byte-for-byte against the accel fields of the same packet on hardware. Trust the
> measurement over the name.

## 5.5 Where to put your code

DMP program memory is **volatile RAM**. There is no flash and no way to brick the part — a power
cycle restores it to stock. Every bench operation that patches also restores.

You cannot add code: **free RAM above the image is unreachable as code** (§1.1). You patch
in place, into the vendor's own runtime-patch slots — the `a3`-padded runs that
`dmp_enable_feature` writes into. In the 1929-byte MotionApps20 image:

| address | `a3` run | notes |
|---|---:|---|
| 1869 | 4 | the first output block's four slots; `1867..1872` including its `9d f1` header |
| **1879** | **10** | the largest single site |
| 1890 | 6 | |
| 1906 | 4 | the second output block; `1904..1909` including its `98 f1` header |
| 1911 | 4 | |

Patching the `9x` header byte as well as the slots is what lets you change *which page* the block
emits from, which is how a custom field selection is built.

Beyond those, the knockout sweep identified 16-byte windows whose removal did not stop the
quaternion — repurposable, at the cost of whatever feature lived there.

## 5.6 End to end

`bench/dmprun.py` assembles, patches, loads, runs, captures and verifies:

```bash
python3 bench/dmprun.py --port /dev/ttyUSB0 \
    --site 1867:6:../programs/telemetry.s \
    --site 1904:6:../programs/telemetry_b.s
```

```
site 1867..1872   was 9d f1 a3 a3 a3 a3   now 9c f1 20 38 a3 a3   (2 refs)
site 1904..1909   was 98 f1 a3 a3 a3 a3   now 99 f1 38 a3 a3 a3   (1 ref)

PREDICTION: packet length = 42 + 4x3 = 54 B
MEASURED  : packet length = 54 B   MATCH
  3f633f79=quat_w  00607f2b=quat_z  1238c937=accel_z
cross-check: 12/12 emitted words matched a stock field in the same packet
RESULT: custom program verified
```

Two independent checks, both made **before** the run: the packet length follows from the number
of emits, and every emitted word must equal the corresponding stock field in the same packet.

## 5.7 The bench rig

MPU-6050 on an ESP32 — `SDA = D21`, `SCL = D22`, `INT = D5`, part at 0x68, host at
`/dev/ttyUSB0`. The ESP32 runs `bench/esp32_dmp_bridge/` and contains **no experiment logic**: it
exposes register access (`G`/`S`), DMP memory (`M`/`N`), FIFO (`F`/`R`) and the interrupt counter
(`I`/`Z`) over serial, so iterating an experiment never needs a reflash. Everything else is
host-side Python in `bench/`.

For a remote rig, `bench/rfc2217_server.py` bridges the serial port over the network; RFC2217
carries DTR/RTS so the auto-reset still works, which plain `socket://` does not.

## 5.8 Measurement discipline

Six specific traps in this project produced confident, wrong results. They are worth reading
before you design an experiment, because every one of them looked like a clean measurement:

1. **Validate the instrument first.** A FIFO negative means nothing without a passing bare-emit
   control in the same run. Reading an already-overflowed FIFO made every cell — including the
   control — read zero, and produced a retracted finding.
2. **One cell is not a measurement.** Two single unrepeated cells suggested the mode bytes
   perturbed ordinary stores; three repeats each showed the values were drift.
3. **Never identify a constant from a rounded decimal.** `f6` was reported as `MIN + 2^-15`
   because every cell sat 0.00003 above the minimum — the real offset was the preserved low half
   of the sentinel, 0x7E7E/2^30, indistinguishable at five decimal places. Print raw hex.
4. **Keep operand pages out of the detector's scrub window.** Operands written inside the
   harness's own sentinel region read back as the sentinel, and every cell trivially agreed with
   the hypothesis.
5. **A single-instruction test cannot see pre-advance semantics.** 40 clean cells measured
   `op&4` as a fixed +4 offset; it is a pre-advance, and the two are identical for one op.
6. **Control-guard every cell, and re-init after a poisoning one.** `bc`/`bd` scramble the core;
   everything measured after one is void.

The general rule that follows: run N control steps with a NOP at the test site, keep the bytes
that are identical across all N as a **stability mask**, and compare only inside the mask. A
change inside the mask is a real effect by construction. Report the mask size and N.

Single-stepping works — halt, zero the interrupt count, enable the DMP, poll until INT fires
once, halt — and the interrupt fires exactly once per step. But a single step is **not
deterministic**: repeating an identical step leaves 84–127 of 512 bytes varying, even with gyro
and accel in standby. About 428 of 512 bytes are stable, and that is the detection surface.
