# P4 — bench protocol (MPU-6050 or ICM-20948 on ESP32)

Rig as built: **SDA = D21, SCL = D22, INT = D5**, the part at I2C 0x68 (or 0x69).

The ESP32 runs `esp32_dmp_bridge.ino` and contains **no experiment logic** — it only exposes
register and DMP-memory access over serial. All experiment logic lives in `dmpbench.py` on the
host, so iterating never requires reflashing.

The bridge **auto-detects the part** at boot (banner `# part mpu|icm addr 68`) and hides what
differs: the ICM's banked registers, its `MEM_BANK_SEL`/`MEM_START_ADDR`/`MEM_R_W` at
0x7e/0x7c/0x7d, and its 16-byte burst limit. `X` scans the bus, `A <addr>` sets the address and
`K mpu|icm` picks the profile by hand, `Y 0|1` drives FSYNC on D4. ICM-side helpers (register map, banked `rd`/`wr`, image
load, DMP start, the `Rig` class the custom-program probes use) are in `icm.py`; the ICM probes
are `probe42.py`–`probe66.py` and their results are ISA2.md Findings 24–27 and manual chapter 8;
`probe67.py`–`probe74.py` are the MPU-6050 re-measures (Findings 28–30); `probe75.py`–`probe77.py` decode the DMP3 `fc` bit test (Finding 31).
Two ICM traps: keep `USER_CTRL.FIFO_EN` set while reading the FIFO, and select register bank 0
before anything else after a reset — the bank survives an ESP32 reset.

## Why this is safe

DMP program memory is **volatile RAM**. There is no flash to brick — a power cycle restores the
part to stock. Every `dmpbench.py` operation that patches also restores the original bytes
afterwards.

## Setup

```bash
pip install pyserial          # already present on this machine
# flash bench/esp32_dmp_bridge/esp32_dmp_bridge.ino via Arduino IDE / arduino-cli
# board: ESP32 Dev Module
```

Two ports are visible (`/dev/ttyUSB0`, `/dev/ttyACM0`); the ESP32 is usually `ttyUSB0` with a
CP2102/CH340 bridge, `ttyACM0` with native USB. `probe` will tell you which responds.

## Phase A — channel bring-up

```bash
python3 dmpbench.py --port /dev/ttyUSB0 probe
```

Expect `WHO_AM_I = 0x68` and write/readback OK at three DMP RAM addresses. **This alone proves
the oracle exists** — if we can write and read DMP RAM, we can run instructions and observe them.

## Phase B — validate the environment

```bash
python3 dmpbench.py --port /dev/ttyUSB0 load ../corpus/images/d79e55736bb5ea91_1929.bin
python3 dmpbench.py --port /dev/ttyUSB0 run
```

Loads the stock MotionApps20 image (the empirically proven MPU-6050 image) and starts the DMP at
entry **0x0400**.

> Note that 0x0400 = **1024**, exactly the code/data boundary derived statically from byte
> statistics and Q30 constant decoding. i2cdevlib writing `0x0400` to register 0x70 is
> independent confirmation of that finding.

Success = FIFO fills and INT edges accumulate. If so, the whole environment is validated and
every subsequent result is trustworthy.

## Phase C — the semantics oracle

```bash
python3 dmpbench.py --port /dev/ttyUSB0 diff --addr 1879 --bytes a8 --size 1024
```

`diff` snapshots all DMP RAM with the stock image running, patches one site, re-runs, snapshots
again, reports **which memory locations changed**, then restores. That is the measurement static
analysis could never make.

### Safe patch sites

NOP-padded runs in the 1929 B image — the vendor's own runtime-patch slots, so writing here is
exactly what the hardware expects:

| Address | `a3` run | Capacity |
|---:|---:|---|
| 1869 | 4 | 4 test bytes |
| **1879** | **10** | **10 test bytes — best site** |
| 1890 | 6 | 6 |
| 1906 | 4 | 4 |
| 1911 | 4 | 4 |

### Experiment matrix

The original P4 matrix, kept as a record of how the bench phase was sequenced. All of it
has been executed; the open questions that remain are in [../UNKNOWNS.md](../UNKNOWNS.md).

| # | Question | Patch | Expected signal |
|---|---|---|---|
| 1 | **Model validation** | `f9,28,30,38` at a CFG slot | FIFO packet grows by 3 registers — *predicted* by the static model, so this tests rig **and** model at once |
| 2 | Op mode 1 | `f9,<reg<<3\|1>` | compare memory delta vs mode 0 |
| 3 | Op mode 2 | `f9,<reg<<3\|2>` | same |
| 4 | `a8` family (69 uses) | `a8` alone | which RAM word moves |
| 5 | `d0`/`d1` | `d0`, then `d1` | |
| 6 | `f2`/`f3` | `f2`, then `f3` | |
| 7 | `88`/`99` | each alone | |

Run experiment 1 first. If the FIFO packet changes exactly as the static model predicts, both
the rig and the `f8+n` block-opcode model are confirmed, and experiments 2-7 become
straightforward reads of the memory-delta output.

## Interpreting a null result

`diff` reporting no changed memory is informative, not a failure — it means the opcode affects
only FIFO output or internal state not mapped into readable RAM. Cross-check with `run` to see
whether FIFO packet size or INT rate changed.
