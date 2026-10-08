# The DMP Programmer's Manual

The Digital Motion Processor in the InvenSense MPU-6050 family (MPU-6050, MPU-6500, MPU-9150,
MPU-9250) and, as DMP3, in the ICM-20948: its architecture, memory, instruction set, host
interface and assembly language.

## Contents

| Chapter | |
|---|---|
| 1 | [Architectural Overview](01-architecture.md): the programmer's model, machine state, execution model |
| 2 | [Memory Organization and Data Types](02-memory.md): memory maps, the sample page, pointers, integer and Q30 words |
| 3 | [Programmer's Guide](03-programmers-guide.md): instruction formats, and each instruction class with examples |
| 4 | [Instruction Set Summary](04-instruction-summary.md): every instruction, its length, cycles and flags |
| 5 | [Instruction Definitions](05-instruction-definitions.md): each instruction in full, A to Z |
| 6 | [Opcode Maps](06-opcode-maps.md): both cores, byte by byte; reserved encodings |
| 7 | [Host Interface](07-host-interface.md): registers, loading, starting, the FIFO, the sample rate |
| 8 | [Assembly Language](08-assembly-language.md): source format, directives, mode tracking |
| 9 | [Programming Techniques](09-programming-techniques.md): complete programs for common tasks |

**Figures**

| Figure | |
|---|---|
| 1-1 | [The programmer's model](figures/block-diagram.svg) |
| 1-2 | [When a pass runs](figures/pass-timeline.svg) |
| 2-1 | [MPU-6050 memory map](figures/memory-map-mpu.svg) |
| 2-2 | [ICM-20948 memory map](figures/memory-map-icm.svg) |
| 2-3 | [How an operand address is formed](figures/address-formation.svg) |
| 2-4 | [Word formats](figures/word-formats.svg) |
| 3-1 | [The mode register](figures/mode-register.svg) |
| 3-2 | [The DMP3 return stack](figures/return-stack.svg) |
| 3-3 | [The DMP3 shifter](figures/shifter.svg) |

## The DMP on One Page

**How it runs.**
- The DMP runs its program once per sensor sample, from the entry point to `end`.
- It has no general-purpose registers. Three pointers name memory words: P0 the A operand, P1 the
  B operand, and P2 the destination.
- An ALU byte combines A and B. The 64-bit result register R takes the result, and the flag F
  takes its sign.
- The result goes through the route, either to memory at P2 or to the FIFO.

**Arithmetic.**
- The words are 32-bit two's complement, read as integers or as Q30 fractions. Only
  multiplication cares which: it keeps ⌊A·B / 2³⁰⌋.
- Multiply-accumulate sums products exactly in R.
- The ALU can work on 16-bit lanes.

**Conditions and branches.**
- Predicates make any run of instructions conditional.
- The MPU-6050 branches up to 32 bytes either way. DMP3 jumps anywhere and has a four-entry return
  stack.

**Two rules.**
- Every branch, jump or call leaves the machine in mode 4. Write `always` and a mode byte at
  every target and after every branch.
- Close every conditional block with `always`.

```asm mpu6050
        .chip   mpu6050
        .entry  0x400
        .org    0x100
k:      .dw     0.25q, 0.5q             ; constants are words the host loads
        .org    0x400
        fmode   1                       ; the ALU's mode: 32-bit arithmetic
        always                          ; no predicate
        fifo                            ; results to the FIFO
        p0bank  1
        p0page  0                       ; P0 -> k
        p1bank  1
        p1page  0                       ; P1 -> k
        add     0,1                     ; emit 0.25 + 0.5
        int                             ; tell the host
        end
        ; expect fifo = 30000000
```

The measurements behind this manual are recorded in [ISA2.md](../../ISA2.md).
