# 7. Host Interface

The host loads the DMP's program and data, starts and stops it, sets the sample rate, and reads
the FIFO. Everything goes through the sensor's I²C (or SPI) registers.

## 7.1 Registers

| Function | MPU-6050 | ICM-20948 |
|---|---|---|
| Register bank select | — | `REG_BANK_SEL` 0x7F (bits 5–4) |
| Identity | `WHO_AM_I` 0x75 = 0x68 | bank 0 `WHO_AM_I` 0x00 = 0xEA |
| Power, device reset | `PWR_MGMT_1` 0x6B (bit 7 resets) | bank 0 `PWR_MGMT_1` 0x06 (bit 7 resets) |
| Sensor enables | `PWR_MGMT_2` 0x6C | bank 0 `PWR_MGMT_2` 0x07 |
| DMP and FIFO control | `USER_CTRL` 0x6A | bank 0 `USER_CTRL` 0x03 |
| FIFO reset | `USER_CTRL` bit 2 | bank 0 `FIFO_RST` 0x68 |
| Interrupt enable | `INT_ENABLE` 0x38, bit 1 DMP_INT | bank 0 `INT_ENABLE` 0x10, bit 1 DMP_INT1 |
| Interrupt status | `INT_STATUS` 0x3A, bit 1 | bank 0 `INT_STATUS` 0x19, bit 1 |
| Sample rate | `SMPLRT_DIV` 0x19, `CONFIG` 0x1A | bank 2 `GYRO_SMPLRT_DIV` 0x00, `ACCEL_SMPLRT_DIV` 0x10–0x11 |
| Full scale | `GYRO_CONFIG` 0x1B, `ACCEL_CONFIG` 0x1C | bank 2 `GYRO_CONFIG_1` 0x01, `ACCEL_CONFIG` 0x14 |
| FSYNC into the sample | `CONFIG` bits 5–3 (`EXT_SYNC_SET` = 1) | bank 2 `FSYNC_CONFIG` 0x52 = 1 |
| DMP memory bank | `BANK_SEL` 0x6D | bank 0 `MEM_BANK_SEL` 0x7E |
| DMP memory address | `MEM_START_ADDR` 0x6E | bank 0 `MEM_START_ADDR` 0x7C |
| DMP memory data | `MEM_R_W` 0x6F | bank 0 `MEM_R_W` 0x7D |
| Entry point (PRGM_START) | `DMP_CFG_1`, `DMP_CFG_2` 0x70–0x71 | bank 2 `PRGM_START_ADDRH`, `L` 0x50–0x51 |
| FIFO count | `FIFO_COUNTH`, `L` 0x72–0x73 | bank 0 `FIFO_COUNTH`, `L` 0x70–0x71 |
| FIFO data | `FIFO_R_W` 0x74 | bank 0 `FIFO_R_W` 0x72 |

`USER_CTRL` bits (both parts):

| Bit | Name | Use |
|---|---|---|
| 7 | DMP_EN | 1: the DMP runs a pass at each sample tick |
| 6 | FIFO_EN | 1: the FIFO accepts data and can be read |
| 3 | DMP_RST | 1: reset the DMP (self-clearing) |
| 2 | MPU: FIFO_RESET; ICM: SRAM_RST | MPU: empty the FIFO. ICM: do not set; use `FIFO_RST` |

## 7.2 Reading and Writing DMP Memory

```text
    MEM_BANK_SEL   := address >> 8           (MPU: BANK_SEL)
    MEM_START_ADDR := address & 0xFF
    burst read or write MEM_R_W              the address increments within the 256-byte bank
```

- **Bank boundaries.** A burst must not cross a 256-byte bank boundary. Split longer transfers.
- **Burst length.** The ICM-20948 accepts bursts of up to 16 bytes, with `REG_BANK_SEL` = 0.
- **Verify.** Read every load back and compare. A failed I²C transfer otherwise looks like a
  program that does nothing.

## 7.3 Loading and Starting a Program

**MPU-6050.**

```text
    PWR_MGMT_1   := 0x80;  wait 100 ms        device reset (DMP memory is kept)
    PWR_MGMT_1   := 0x01;  wait 20 ms         wake; PLL on the X gyro
    USER_CTRL    := 0x00
    SMPLRT_DIV   := 1000 / rate - 1           one pass per sample (CONFIG's DLPF on: 1 kHz base)
    CONFIG       := 0x03                      DLPF 42 Hz; | 0x08 for FSYNC in the sample
    GYRO_CONFIG, ACCEL_CONFIG := full scales
    INT_ENABLE   := 0x02                      DMP_INT
    write zeros to 0x000-0xBFF, then the program and its data; read them back
    DMP_CFG_1    := entry >> 8;   DMP_CFG_2 := entry & 0xFF
    USER_CTRL    := 0x4C                      FIFO_EN | DMP_RST | FIFO_RESET
    USER_CTRL    := 0xC0                      DMP_EN | FIFO_EN: running
```

**ICM-20948.**

```text
    bank 0: PWR_MGMT_1 := 0x80;  wait 100 ms  device reset (writes 0x0080-0x0087; keeps the rest)
    bank 0: PWR_MGMT_1 := 0x01;  wait 20 ms   wake, auto clock
    bank 0: PWR_MGMT_2 := 0x00;  LP_CONFIG (0x05) := 0x00;  USER_CTRL := 0x00
    bank 2: GYRO_SMPLRT_DIV := 1100 / rate - 1;  ACCEL_SMPLRT_DIV := the same
    bank 2: GYRO_CONFIG_1, ACCEL_CONFIG := full scales with the DLPF on
    bank 2: FSYNC_CONFIG := 0x01 for FSYNC in the sample, else 0x00
    bank 0: INT_ENABLE := 0x02                DMP_INT1;  FIFO_EN_1, FIFO_EN_2 := 0
    write zeros to 0x0000-0x2FFF, then the program and its data; read them back
    bank 2: PRGM_START_ADDRH := entry >> 8;  PRGM_START_ADDRL := entry & 0xFF
    bank 0: FIFO_RST := 0x1F, then 0x1E
    bank 0: USER_CTRL := 0x08                 DMP_RST
    bank 0: USER_CTRL := 0xC0                 DMP_EN | FIFO_EN: running
```

After DMP_RST the machine is in the state of §1.3:
- the route is RAM;
- the pointers are at 0;
- the mode is 32-bit;
- F and R are 0.

**Stopping.**

| To | Write | Effect |
|---|---|---|
| stop at the end of the pass | `USER_CTRL` := 0x40 (ICM: keep FIFO_EN, so the FIFO stays readable) | No new pass starts; a pass already running continues to its `end`. |
| stop at once | `USER_CTRL` := 0x48, then 0x40 | DMP_RST halts a running pass, including one that never ends. |

**Two ICM-20948 rules.**
- `FIFO_EN` must stay set while the FIFO is read. With it clear, `FIFO_R_W` returns one fixed byte
  and the count does not move.
- The register bank survives a reset of the host controller. Select bank 0 before reading
  `WHO_AM_I`.

## 7.4 The FIFO

The FIFO holds exactly what the program emits, in order. The hardware adds no header, footer or
sample data of its own.
- Every emitted word adds 4 bytes, and every lane item 2.
- A program's packet length is therefore known before it runs.

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Capacity | 1024 B | 4096 B |
| Location | separate from DMP memory | DMP memory 0x3000–0x3FFF, filled from 0x3000 after a FIFO reset |
| Overflow | the oldest bytes are lost; the count stays at 1024 | the oldest bytes are lost; the count stays at 4096 |

To drain the FIFO, read `FIFO_COUNTH:L`, then burst-read that many bytes from `FIFO_R_W`. The count
does not show packet boundaries, so read whole packets. If the FIFO can overflow before the host
drains it, the bytes lost are the oldest, and the remaining data may begin part-way through a
packet.

## 7.5 Sample Rate and Scheduling

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Sample rate | 1 kHz / (1 + `SMPLRT_DIV`), DLPF on | 1.1 kHz / (1 + `GYRO_SMPLRT_DIV`) |
| Pass start | 110 cycles after the tick | 130 cycles after the tick |
| An overrunning pass | the next pass waits for the next tick | the next pass starts about 150 cycles after `end` |

<a id="budget"></a>The pass budget is the sample period less the start latency. Table 4-1 gives it in cycles, ADDs
and MOVs. For a straight-line program, the worst-case pass time is the sum of the cycle counts of
the longest path. For a program with loops, add each loop body's cost multiplied by its trip count.

## 7.6 The Interrupt

The DMP's `int` instruction sets DMP_INT (MPU) or DMP_INT1 (ICM) in `INT_STATUS` and drives the
INT pin when `INT_ENABLE` enables it. A program usually raises it once per pass, after its last
emit, so the host reads the FIFO only when a packet is complete.

## 7.7 Running Programs

The `opendmp` tools assemble, list and emulate DMP programs (Chapter 8):

```text
    python -m opendmp asm prog.asm                  listing: address, bytes, instruction, effect, cycles
    python -m opendmp asm prog.asm -o prog.bin      the memory image, to load at address 0
    python -m opendmp dis prog.bin --chip mpu6050   disassemble a binary
```

In Python, the emulator runs a pass over a given sample:

```python
from opendmp.isa import assemble
from opendmp.emu import Machine, Sample

prog = assemble(open("prog.asm").read())
m = Machine(prog.chip)
for addr, data in prog.segments():
    m.load(data, addr)
m.entry = prog.entry
result = m.run_pass(Sample(ax=100, gz=-5))    # FIFO bytes, interrupts and cycles of one pass
```

## 7.8 The Bench Rigs

Two rigs, one per part. Each is an ESP32 bridge with the sensor on SDA = D21 and SCL = D22, INT on
D5, and FSYNC driven from D4 (ICM rig). The ESP32 holds no experiment logic. It answers a line
protocol over USB serial:

| Command | Effect |
|---|---|
| `G reg n`, `S reg hex` | read, write registers |
| `M bank addr n`, `N bank addr hex` | read, write DMP memory |
| `F`, `R n` | FIFO count, read the FIFO |
| `I`, `Z` | interrupt count, clear it |
| `T ms` | reset and start the DMP, wait for one interrupt, stop it; returns the count and the time |
| `W ms` | as `T`, and timestamp the first two interrupts |
| `Y 0` / `Y 1` | drive FSYNC |

`opendmp.host.Rig` drives the protocol from Python. `bench/` holds the bridge firmware and the
measurement scripts.
