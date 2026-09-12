# The InvenSense DMP Programmer's Manual

A working reference for **writing programs** for the Digital Motion Processor embedded in the
MPU-6050 / 6500 / 9150 / 9250 family, and — [chapter 8](08-dmp3-icm20948.md) — the ICM-20948's
DMP3. The instruction set was never published; everything here was recovered from vendor
firmware images and confirmed on MPU-6050 and ICM-20948 bench rigs.

| chapter | contents |
|---|---|
| [01 — Machine model](01-machine-model.md) | memory, Q30 arithmetic, the three pointers, machine state, execution model |
| [02 — Instruction set](02-instruction-set.md) | every encoding, normative. The complete 256-entry map |
| [03 — Assembly language](03-assembly-language.md) | `dmpasm` mnemonics, directives, patching a host image |
| [04 — Idioms](04-idioms.md) | how to do the things the ISA has no instruction for |
| [05 — Host interface](05-host-interface.md) | I²C load and start sequence, FIFO packets, patch sites, the bench rig |
| [06 — Memory map](06-memory-map.md) | address arithmetic, the constant page, sensor inputs, scratch, symbols |
| [07 — Limits and open questions](07-limits.md) | what the machine cannot do, and what is still unknown |
| [08 — The ICM-20948 (DMP3)](08-dmp3-icm20948.md) | what differs on the DMP3 core: 16 KB, block pointers, 16-bit jump/call/return, branch-target mode and the I/O space, sticky predicates and the sign flag, the 4-word shifter, the interrupt |

Companion documents outside the manual:

- [`ISA2.md`](../../ISA2.md) — the evidence log. Every rule in this manual traces to a numbered
  finding there, with the experiment that established it and the corrections along the way.
- [`FIRMWARE.md`](../../FIRMWARE.md) — what the *shipped* firmware computes, stage by stage.
- [`UNKNOWNS.md`](../../UNKNOWNS.md) — the open items, and the experiment that would settle each.

## In one page

The DMP is a **Q30 fixed-point, feed-forward, pointer-addressed accumulator machine**.

- All state is data RAM plus three pointers, a 2-bit destination-word index, a zero flag, and a
  handful of sticky mode latches. There are no general registers and no immediate operands.
- One instruction is one byte. The only two-byte instruction is the branch, and only when it
  actually branches.
- The ALU does add, reverse-subtract, multiply, negated multiply and signed minimum, on 32-bit
  Q30 words. It **wraps** rather than saturating. There is no divide, no shift, no logic op.
- Results go wherever a sticky latch points — RAM or the output FIFO. There is no store
  instruction and no push instruction; there is a *routing* instruction.
- Control flow is a **forward-only** 7-bit branch, optionally under a zero test, plus halt.
  No loops, no calls, no stack, no return. (DMP3 replaces the branch with a 16-bit jump, adds
  call and return, and so has loops — chapter 8.)
- The program is re-run from the top on every sample interrupt. It must finish inside one
  sample period, which is why forward-only control flow is enough.

```
        selbank quat            ; P1 -> the quaternion page
        emit    quat_w, quat_z  ; two ALU adds of 0.0, routed to the FIFO
```

That fragment, patched into a stock image, makes the DMP emit a field selection the vendor
firmware never produces. See [chapter 3](03-assembly-language.md).

## How to read the status tags

Reverse engineering earns claims; it does not assume them. Every statement in this manual carries
one of three tags, and they mean exactly this:

| tag | meaning |
|---|---|
| **[HW]** | measured on MPU-6050 silicon, with a passing control in the same run, repeated |
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
