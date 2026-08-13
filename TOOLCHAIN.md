# Toolchain plan — disassembler, assembler, and running custom DMP code

Target: MPU-6050 on the ESP32 rig, MotionApps20 (1929 B) as the host image.
Strategy: build the tooling around what is **confirmed**, mark the rest UNKNOWN, and let the
same tooling be the instrument that fills the gaps.

## Resources measured on the bench

| resource | value |
|---|---|
| addressable DMP RAM | `0x0000`–`0x0BFF` = **3072 B** |
| host image | 1929 B |
| **free RAM above image** | **1143 B (1929–3071), verified untouched across a run** |
| patchable operand slots | 4 at 1868 + 4 at 1905 = **8 register slots** |
| non-critical code windows | from the knockout sweep — 16-byte windows whose removal did *not* stop the quaternion, i.e. repurposable |
| branch reach | **none known** — `f4` is not a branch (round 9). No control-flow primitive is confirmed. |

## Confirmed instruction set (what the toolchain is built on)

```
9x           SELBANK n      select source bank for following register refs
f8+n         BLOCK          block opcode; n selects the operation (n=1 emits to FIFO)
<low byte>   register ref    (reg = v>>3); consumed by the preceding block; emits 4 B (Q30)
             bit 1 set      -> reads as zero, inert
a3           NOP            DINAA0+3; filler, used to disable code in place
f4 <imm>     UNKNOWN.imm    2 bytes; immediate alters output composition.
                            NOT a branch - see RESULTS.md round 9 (retracted)
fe / ff      SKIP / DISABLE block-level disable
```

Register map (position-dependent — the read site matters):

| bank | indices | contents |
|---|---|---|
| `0x9a` | `28 30 38` | gyro x, y, z |
| `0x9c` | `20 28 30 38` | quat w, x, y, z |
| `0x99` | `28 30 38` | accel x, y, z (post-accel site) |
| `0x98` | `28 … 38` | delay line (t, t−1) |

---

# Phase T1 — disassembler — DONE (`tools/dmpdis2.py`)

`tools/dmpdis2.py`, replacing the byte-at-a-time decoder with a **context-sensitive** one. This
is the key correctness point: after a block opcode the following low bytes are *operands*, not
instructions, so a linear decoder is wrong by construction.

State machine:

- `9x` → `SELBANK n`; record current bank for naming
- `f8+n` → `BLOCK.n`; enter operand mode
- operand mode: consume low bytes (`<0x80`) as register refs; resolve to `gyro_x`, `quat_w`, …
  when the bank is known; exit on the first high byte
- `f4` → 2-byte `f4.imm`, flagged `[?]` (not a branch; function unknown)
- `a3`/`fe`/`ff` → `NOP`/`SKIP`/`DISABLE`
- anything else → `family.index`, confidence `[?]`

Passes: (1) linear decode with context, (2) region classification (data below 1024, code
above), (3) confidence summary. No branch-target pass — no branch instruction is known.

**Delivered.** Context-sensitive decoder with lineage detection (6050 vs Mantis opcode
numbering), bank-state tracking, and register naming from the hardware-verified map.

**Validated against silicon.** Decoding MotionApps20 from the code start reproduces the entire
output section, including bank state carried across intervening instructions:

```
1853  9c              SELBANK 0x9c
1857  f1 20 28 30 38  EMIT  16 B  [quat_w, quat_x, quat_y, quat_z]
1862  9a              SELBANK 0x9a
1863  f1 28 30 38     EMIT  12 B  [gyro_x, gyro_y, gyro_z]
1899  99              SELBANK 0x99
1900  f1 28 30 38     EMIT  12 B  [accel_x, accel_y, accel_z]
```

16+12+12 = 40 + 2-byte footer = **42 B, exactly the measured packet length**.

Corpus-wide verified-instruction share:

| size | lineage | instr | [C] | [P] | [?] | %verified |
|---:|---|---:|---:|---:|---:|---:|
| 1024 | 6050 | 955 | 160 | 794 | 1 | 16.8% |
| 1929 | mantis | 869 | 150 | 719 | 0 | 17.3% |
| 2639 | mantis | 1538 | 189 | 1325 | 24 | 12.3% |
| 3065 | mantis | 1957 | 309 | 1630 | 18 | 15.8% |
| 14301 | mantis | 9785 | 1185 | 8344 | 256 | 12.1% |

`[P]` means placed in a named vendor family, semantics unknown — it is not knowledge. The honest
figure is the `[C]` column: **12–18% of instructions have verified behaviour.**

# Phase T2 — assembler — DONE (`tools/dmpasm.py`)

`tools/dmpasm.py`. Small, honest language covering exactly the confirmed subset:

```
    selbank 0x9a
    emit    gyro_x, gyro_y, gyro_z
    nop
    .db     0xd8            ; escape hatch for unknown opcodes
```

Requirements:
- assemble to bytes; **round-trip verified against `dmpdis2.py`**
- patch mode: write into a named site in a host image with **size checking** — a block has a
  fixed slot count and overrunning it corrupts the next instruction
- refuse to emit anything not in the confirmed set unless `.db` is used explicitly

# Phase T3 — custom program on the 6050 — DONE (`bench/dmprun.py`)

`bench/dmprun.py`: assemble → patch → load → run → capture → decode → verify.

**First program** — a telemetry configuration the stock firmware never produces, e.g. gyro x/y/z
plus quat_w in one custom block:

```
    selbank 0x9a
    emit    gyro_x, gyro_y, gyro_z
    selbank 0x9c
    emit    quat_w
```

Self-verifying in two independent ways:
1. **Predicted packet length** = 42 + 4×(refs) bytes; must match the measured footer-to-footer
   gap exactly.
2. **Cross-check** the emitted words against the stock packet's own gyro/quat fields.

**Result — verified on silicon.** Two sites patched from source:

```
site 1867..1872   was 9d f1 a3 a3 a3 a3   now 9c f1 20 38 a3 a3   (2 refs)
site 1904..1909   was 98 f1 a3 a3 a3 a3   now 99 f1 38 a3 a3 a3   (1 ref)

PREDICTION: packet length = 42 + 4x3 = 54 B
MEASURED  : packet length = 54 B   MATCH

  3f633f79=quat_w  00607f2b=quat_z  1238c937=accel_z
  3f5dec14=quat_w  0062c831=quat_z  123bdca7=accel_z
  3f588b85=quat_w  00650ded=quat_z  124423e7=accel_z

cross-check: 12/12 emitted words matched a stock field in the same packet
RESULT: custom program verified
```

The DMP now emits `quat_w, quat_z, accel_z` — a selection the stock firmware never produces —
written in our own assembly, assembled by our own assembler, with the packet layout predicted
before the run and confirmed byte-for-byte.

This is a genuine custom DMP program. It is *not* arbitrary computation — see the ceiling below.

# Phase T4 — semantic discovery engine — FIRST PASS DONE (`bench/discover.py`)

The reason to build T1–T3 first: the emit block is a **general readout**. Any bank/index can be
read on demand, which turns opcode discovery into a systematic sweep instead of guesswork.

Harness:
- **site A** (block at 1868) — overwrite with `<candidate> a3 a3 a3 a3`; the candidate executes
- **site B** (block at 1905) — readout block emitting a chosen register set
- compare register values with candidate vs `a3` control
- sweep candidate over all 256 byte values, and over 2-byte forms for suspected operand-takers

Outputs per candidate: registers changed, quaternion integrity, packet-length delta, whether the
DMP survives. Crashes are expected, detectable, and recoverable (restore + restart).

This is the mechanism that fills in the ~3 of 4 instructions currently unattributed — most
valuably any instruction that **writes** a register, which we have never observed.

# Phase T5 — hosted code in free RAM — DONE, NEGATIVE

Executed. Free RAM was filled with four different byte values (`a3`, `ff`, `00`, `d8`) and
`f4 <imm>` swept across it; **outcomes were identical for every fill**, so execution never
reaches the region. The 1143 bytes are addressable *data* storage only.

Custom code is therefore confined to in-place operand slots and repurposable non-critical
windows. See RESULTS.md round 9.

---

# How far can we actually go

**Reachable, high confidence:**
- Complete context-sensitive disassembler over the whole corpus
- Assembler for the confirmed subset, round-trip verified
- Custom telemetry programs on real silicon with exactly predicted behaviour
- Feature enable/disable patching (already demonstrated)

Net: a **DMP telemetry and feature compiler** — you control what the DMP emits and which
features run, with verification.

**Likely with T4:** semantics for a substantial share of the high opcode space, including
register writes and arithmetic, discovered systematically rather than inferred.

**Genuinely uncertain — the honest ceiling:**
- **Control flow.** **No branch instruction is known at all** — `f4` was the candidate and it is
  not one (round 9). No jump, loop, call or return has been observed anywhere. Without any
  control-flow primitive, arbitrary algorithms are not merely hard, they are unexpressible.
- **Writes.** Every confirmed instruction reads. No instruction is yet known to store a value.
- **Standalone programs.** Entry is fixed at the host program's start and the DMP is invoked
  per-sample by hardware; we patch an existing program rather than author one from scratch.

So: *"write custom DMP programs"* in the sense of **reconfiguring what the DMP computes and
emits** — yes, now. In the sense of **compiling arbitrary algorithms to the DMP** — not yet, and
that depends on T4 turning up writes and backward control flow. That is the single question that
decides whether a general assembler is possible.

# Sequencing

T1 → T2 → T3 gives a working, useful toolchain and a custom program running on your hardware,
with everything verified. T4 then runs continuously against it, and each discovery is a one-line
addition to the disassembler's table. T5 is complete and negative, so T4's highest-value targets
are now (a) any instruction that **writes** a register and (b) any **control-flow** primitive —
those two decide whether a general assembler is possible at all.

An MPU-6500/6515 breakout remains the cheapest accelerator: it unlocks the 2639 image whose
validated symbol table names ~166 locations, which would seed T4 with ground truth instead of
blind sweeping.
