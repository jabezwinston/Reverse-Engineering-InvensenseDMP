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
are `probe42.py`–`probe66.py` and their results are ISA2.md Findings 24–27 and the manual's per-core notes;
`probe67.py`–`probe74.py` are the MPU-6050 re-measures (Findings 28–30); `probe75.py`–`probe77.py` decode the DMP3 `fc` bit test (Finding 31); `probe78.py`/`probe79.py` run the 2639 image on the 6050 (Finding 32). `probe80.py`/`probe80b.py` (ICM) and `probe81.py`/`probe81b.py` (MPU) measure the compiler limits: return-stack depth, indirect addressing, MPU jump/call forms (Finding 33); `probe82.py`/`probe82b.py` map the DMP3 I/O space and the sensor-sample RAM (Finding 34). `probe83.py`–`probe83e.py` (ICM) and `probe84.py`/`probe84b.py` (MPU) close the residue: the `fc` immediate compare, FSYNC, `bf`, the MPU block field and sample page (Finding 35); `probe85.py` enables the 2639 image's FIFO output (Finding 36). With two rigs, the MPU-6050 bridge is `/dev/ttyUSB0` and the ICM-20948 bridge `/dev/ttyUSB1`.
`probe86.py` (MPU) and `probe88.py` (ICM) run every cell on silicon *and* in the opendmp emulator side by side (Finding 37); `probe87.py`/`probe89.py`/`probe90.py` time opcodes (Finding 38) — `probe90` with the bridge's **`W <ms>`** command: like `T`, but it reports the times of the first two interrupt edges, so `INT <body> INT` times the body without start jitter.
`probe91.py` (either rig) answers opendmp's B1/B2: a program with no vendor image from zeroed memory, the RAM the hardware writes, and where the FIFO lives (Finding 39).
`probe92.py`–`probe101.py` isolate what opendmp's first compiled programs found on silicon (Finding 40): MOV/CLR/INC under every mode, when CMP stores, MPU mode 4 after `f4`, the CMP/RSUB/ADD/MUL/MIN flag rules over full operand matrices, RSUB at −2.0, and the MPU branch as a signed 6-bit field.
`probe102.py` runs the 2026-09 manual's chapter 4 MPU idioms as written (dmpasm source), on silicon and in the emulator: a counted loop with a backward branch, and min by compare-and-skip, including its failure at y = −2.0.
`probe103.py` sweeps `f5` op 0 (long read as MIN) over 1920 cells per part — value, flag and both lanes — and finds a symmetric clamp of A to [−B, B] with F := clamped (Finding 41).
`probe104.py` maps the MPU's mode-4 low bytes with a counting sled over all of RAM: a byte below 0x40 is a one-byte branch (to its address + 1 + sext6), predicable, 10 cycles taken (Finding 42).
`probe105.py` shows that `EXT_SYNC_SET = 1` puts the FSYNC level into the MPU's DMP sample page (temperature bit 0), as on the ICM (Finding 43).
`cells.py` is the shared harness from probe106 on: one pass of an opendmp-assembly program on a rig and in the emulator, side by side, with probe100's F markers.
`probe106.py` takes the multiplier past 2.0: MUL/NMUL wrap mod 2³² with F the exact sign, and the MAC register is 64 bits (Q60 in [−8, 8), F its sign bit) (Finding 44).
`probe107.py` asks what `test` reads: the result register R (the MAC accumulator), at the lane in force; which ops write R (CLAMP writes its compare), which leave it, and the MPU's P2 moves zeroing it (Finding 45).
`probe110.py` (ICM) multiplies integers with `mul` + `shl 30`, and shows that every op that writes R loads the shifter from it and that `lo` reads R's low bits (Finding 46).
`probe109.py` is about pass control: mode bytes under a false predicate, overrunning and endless passes (no vector; DMP_EN does not stop a running pass, DMP_RST does), the sample page rewritten under a long pass, DMP3's return stack across passes, and DMP3 `fe` (Finding 47).
`probe108.py` checks the memory limits: the MPU's top 32 bytes are ordinary code and data, 0xc00 on reads 0, and ICM code runs from 0x0100 up to 0x2fff (Finding 48).
`probe111.py` times every remaining cycle class with `W` (lanes, logic, clear aliases, interrupts, call/ret, bare mode-4 targets, ICM end-to-next-pass) (Finding 49).
`probe112.py` routes INC/DEC to the FIFO: the MPU emits M[P2] ± 1 as a new item, DMP3 changes the last word (Finding 50).
`probe113.py` reads the state a pass starts with: after DMP_RST (RAM routing, pointers at 0, a 32-bit mode, F clear, R = 0) and carried between passes (route, mode, F and R on both; pointers on the MPU only), and finds the ICM's device reset writing 0x0080–0x0087 (Finding 51).
`probe114.py` overfills the FIFO: 1 KB on the MPU, a 4 KB ring on the ICM, the newest bytes kept (Finding 52).
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

## Measurement discipline

Eight specific traps in this project produced confident, wrong results. They are worth reading
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
6. **Control-guard every cell, and re-init after a poisoning one.** `bc`/`bd` move a pointer's
   1 KB block and the MPU keeps it across passes (Finding 35), so one stray block byte shifts
   everything measured after it until `DMP_RST`.

7. **Opposite-sign operands hide a sign test.** Every early cell of the `f5` "compare" had
   operands of opposite sign, where F := A < 0 ≤ B and F := A − B < 0 agree. It was recorded as
   a compare for two findings, until a compiled program disagreed with the emulator on silicon
   (Finding 40). Choose operands on which the candidate rules disagree.
8. **Sweep the whole field, and look at where it lands.** "Forward only, no loop" came from
   sweeping the branch immediates with bit 7 set. Nobody located the landing point of
   `f4 20`–`3f`, which branch backwards (Findings 15, 40).

The general rule that follows: run N control steps with a NOP at the test site, keep the bytes
that are identical across all N as a **stability mask**, and compare only inside the mask. A
change inside the mask is a real effect by construction. Report the mask size and N.

Single-stepping works — halt, zero the interrupt count, enable the DMP, poll until INT fires
once, halt — and the interrupt fires exactly once per step. But a single step is **not
deterministic**: repeating an identical step leaves 84–127 of 512 bytes varying, even with gyro
and accel in standby. About 428 of 512 bytes are stable, and that is the detection surface.
