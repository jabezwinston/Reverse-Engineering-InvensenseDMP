# The InvenSense DMP Programmer's Manual

A working reference for **writing programs** for the Digital Motion Processor embedded in the
MPU-6050 / 6500 / 9150 / 9250 family, and — [chapter 8](08-dmp3-icm20948.md) — the ICM-20948's
DMP3. The instruction set was never published; everything here was recovered from vendor
firmware images and confirmed on MPU-6050 and ICM-20948 bench rigs.

| chapter | contents |
|---|---|
| [01 — Machine model](01-machine-model.md) | memory, Q30 arithmetic, the three pointers, machine state, execution model |
| [02 — Instruction set](02-instruction-set.md) | every encoding, normative: the flag, the lanes, the signed branch and mode 4. The complete 256-entry map |
| [03 — Assembly language](03-assembly-language.md) | `dmpasm` mnemonics, directives, patching a host image |
| [04 — Idioms](04-idioms.md) | how to do the things the ISA has no instruction for: compare, clamp, min/max, loop |
| [05 — Host interface](05-host-interface.md) | I²C load and start sequence, FIFO packets, patch sites, the bench rig |
| [06 — Memory map](06-memory-map.md) | address arithmetic, the constant page, sensor inputs, scratch, symbols |
| [07 — Limits and open questions](07-limits.md) | what the machine cannot do, and what is still unknown |
| [08 — The ICM-20948 (DMP3)](08-dmp3-icm20948.md) | what differs on the DMP3 core: 16 KB, block pointers, 16-bit jump/call/return, branch-target mode and the I/O space, the three-byte zero test, sticky predicates and the frozen flag, the 4-word shifter, the interrupt |

Companion documents outside the manual:

- [`ISA2.md`](../../ISA2.md) — the evidence log. Every rule in this manual traces to a numbered
  finding there, with the experiment that established it and the corrections along the way.
- [`FIRMWARE.md`](../../FIRMWARE.md) — what the *shipped* firmware computes, stage by stage.
- [`UNKNOWNS.md`](../../UNKNOWNS.md) — the open items, and the experiment that would settle each.

## In one page

The DMP is a **Q30 fixed-point, pointer-addressed machine with a multiply-accumulator, re-run once per sample**.

- **State.** All state is data RAM plus:
  - three pointers and a 2-bit destination-word index;
  - **one flag**, the sign of the last result computed exactly;
  - a mode register;
  - a handful of sticky latches.

  There are no general registers and no immediate operands.
- **Encoding.** One instruction is one byte. The only two-byte instruction is the branch, and
  its interrupt form.
- **Arithmetic.** The ALU does add, reverse-subtract, multiply, negated multiply and
  multiply-accumulate on 32-bit Q30 words or 16-bit lanes; under another mode it does a
  symmetric CLAMP (long read as MIN), AND and XOR. It **wraps** rather than saturating, but the flag sees the exact result, so a
  subtraction is a compare that cannot overflow. There is no divide and no shift.
- **Routing.** Results go wherever a sticky latch points: RAM or the output FIFO. There is no
  store instruction and no push instruction; there is a *routing* instruction.
- **Control flow.** A **signed 6-bit** relative branch (−32..+31 bytes), under a sign or zero
  test, plus end-of-pass. So loops are possible; calls, a stack and a return are not. Every
  branch leaves **mode 4**, where the next ALU byte would be read as a one-byte branch, so a program sets
  the mode again after each one. (DMP3 has a 16-bit jump, call and return — chapter 8.)
- **Timing.** The program is re-run from the top on every sample interrupt and must finish
  inside one sample period. Every instruction costs a fixed number of clock cycles.

```
        selbank quat            ; P1 -> the quaternion page
        emit    quat_w, quat_z  ; two ALU adds of 0.0, routed to the FIFO
```

That fragment, patched into a stock image, makes the DMP emit a field selection the vendor
firmware never produces. See [chapter 3](03-assembly-language.md).

> **Revised 2026-09-23 for ISA2.md Findings 37–42.** Every chapter now reflects them. Findings
> 37–38, 40 and 41 were measured for the opendmp compiler (`~/Git_repos/opendmp`), whose emulator
> encodes all of this and whose 12 example programs run bit-exact on both parts.
> - **The flag.** One flag F on both cores: the exact result's sign, or == 0 after `d1`. There
>   is no Z.
> - **Lanes.** `f2`/`f3` are 16-bit lanes the ALU computes in.
> - **The MAC.** `f0` is the multiply-accumulator. It restarts when the MPU's destination
>   moves.
> - **Timing** is in integer clock cycles.
> - **No vendor image is needed.**
> - **Branches.** The MPU's branch is signed and can loop, and every `f4` leaves mode 4.
> - **Compares.** The `f5` "compare" only tests signs; a compare is an RSUB.
> - **CLAMP.** The `f5` "MIN" clamps A to [−B, B] (Finding 41).
> - **One-byte branches.** In the MPU's mode 4 a byte below 0x40 is a one-byte branch (Finding 42).
>
> Where a chapter changed, it says what the earlier edition claimed and why that was wrong.

## How to read the status tags

Reverse engineering earns claims; it does not assume them. Every statement in this manual carries
one of three tags, and they mean exactly this:

| tag | meaning |
|---|---|
| **[HW]** | measured on silicon (MPU-6050; ICM-20948 in chapter 8), with a passing control in the same run, repeated |
| **[VENDOR]** | read off vendor source: driver patch pairs, `dmpKey.h`, `dmpmap.h` symbol tables |
| **[INFER]** | derived from the model or the corpus, consistent with everything measured, **not** itself measured |

Untagged prose is description, not claim. Where a **[HW]** tag names a probe (`probe31`), the
script is in [`bench/`](../../bench/) and re-runnable against a rig.

## Coverage, stated exactly

Decoding the 11 MPU-6050-family corpus images end to end under the model in chapter 2:

| | |
|---|---|
| code bytes decoded | **17297** |
| bytes with no meaning at all | **0** |
| bytes rendered as marked conjecture | **13** |
| hardware-confirmed share | **99.92 %** |

The 13 are twelve 3050-lineage `c8`–`cf` and one 3050 `ff` — a different part, which this bench
cannot test (see [chapter 7](07-limits.md)). The ICM-20948 image is a different DMP generation
and is **out of scope**: under this model it decodes to 93.1 %, which is an upper bound on
coincidental agreement, not a decode.

Reproduce with:

```bash
python3 tools/isa/decode.py corpus/images/2e40b3ba8a7227f9_1923.bin   # annotated listing
python3 tools/isa/pseudo.py corpus/images/2e40b3ba8a7227f9_1923.bin   # C-like pseudo-code
python3 tools/isa/pseudo.py <image> --check                           # decoder self-consistency
```

`decode.py` is current. `pseudo.py` predates Findings 27–40: it renders predicates as
single-shot tests of a Z flag. Read its output against chapter 2.
