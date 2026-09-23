# 6. Memory map

## 6.1 Two different address spaces

These are routinely conflated and they are not the same size.

| space | range | reached by |
|---|---|---|
| **host-addressable DMP RAM** | `0x000`–`0xBFF`, 3072 B | `BANK_SEL` / `MEM_START_ADDR` / `MEM_R_W` **[HW]** |
| **program-addressable RAM** | `0x000`–`0x3FF`, **1024 B** per block; all 3072 B with the block field | P0 / P1 / P2, `bc`/`bd`/`be` **[HW]** |

A pointer is `bank * 256 + page * 16` with a 4-bit page and a **2-bit bank**, so the largest
address any pointer can name is `3*256 + 15*16 + 12` = 1020 — within one **block**. No MPU
image uses the block field, but the core has it: `bc`/`bd`/`be` add 1 KB to P0/P1/P2 modulo 3,
so the program reaches all 3072 bytes **[HW, probe84/84b]**. Unlike DMP3, the block is **not
reset at the start of a pass**: it accumulates across passes until `DMP_RST`, so a program that
moves a pointer's block must bring it back (three `bc` in all) before the pass ends. That is
why a stray `bc` "scrambled" the vendor image in the early probes.

The older 3050 core had a **1-bit** bank field, giving 512 B — and `dmpmap.h`, the vendor's
symbolic data map, describes exactly 512 bytes. The mantis core widened the field by one bit,
which is the "register index widened" remap that fell out of image diffing before the vendor
header confirmed it **[VENDOR]**.

Consequences worth stating plainly:

- **Free RAM above the image is host-addressable but not program-addressable**, and not
  executable either. The 1143 free bytes in the 1929-byte host image are storage for the host,
  not memory for the DMP program.
- In **Family B** images (code from 1024) the pointer window and the code region do not overlap:
  all 1024 addressable bytes are data.
- In **Family A** images (code from 768) the pointer window covers `768`–`1023` — **a quarter of
  the addressable space is the program's own code.** A stray P2 there corrupts the program.

## 6.2 Addressing

```
    address(P) = bank * 256 + page * 16              page = 0..15   bank = 0..3

    A operand  = M[ address(P0) + 4*A ]              A, B = 0..3, from the ALU byte
    B operand  = M[ address(P1) + 4*B ]
    destination= M[ address(P2) + 4*p2word ]         p2word = the walked 2-bit index
```

A page is four 32-bit words, and it is the natural allocation unit: an ALU instruction can reach
all four words of each operand page with no pointer reload, and `df`/`d0`/`inc` walk the
destination through all four.

**Design your data in pages of four.** The vendor firmware does exactly that — `QT1..QT4`,
`TMP1A..TMP4A`, `CTRL1..CTRL4`, `ACCQD0..ACCQD3` — because it makes the four-word idioms fall out.

## 6.3 The data map

`dmpmap.h` names 247 addresses across the 512 bytes of the 3050 window **[VENDOR]**. It is
written for `dmpDefaultMantis.c` (corpus image 1923); names are approximate for other images.
`H` suffixes mark the high half of a 32-bit quantity and are stripped in listings.

| addr | page | word 0 | word 1 | word 2 | word 3 |
|---:|---:|---|---|---|---|
| 0 | 0 | `PTAT` | `YGYR` | `XACC` | `ZACC` |
| 16 | 1 | `ADC2` | `BIASUNC` | `INVGSF` | `1H` |
| 32 | 2 | `BLPFSTC` | `BLPFSX` | `BLPFSY` | `BLPFSZ` |
| 48 | 3 | `BLPFMTC` | `BLPFMX` | `BLPFMY` | `BLPFMZ` |
| 64 | 4 | `BLPFC` | `0H2` | `BERR2` | `BERR2N` |
| 80 | 5 | `ANGVBX` | `ANGVBY` | `ANGVBZ` | `BERR1` |
| 96 | 6 | `ATC` | `ACT2` | `GSF` | `G` |
| **112** | **7** | **`0_5`** | **`0_0`** | **`1_0`** | **`1_5`** |
| 128 | 8 | `TMP1A` | `TMP2A` | `TMP3A` | `TMP4A` |
| 144 | 9 | `XACCW` | `XACCB` | `YACCB` | `ZACCB` |
| 160 | 10 | `DZ` | `XGC` | `YGC` | `ZGC` |
| 176 | 11 | `YACCW` | `AFB1` | `AFB2` | `MAGFB` |
| 192 | 12 | `QT1` | `QT2` | `QT3` | `QT4` |
| 208 | 13 | `CTRL1` | `CTRL2` | `CTRL3` | `CTRL4` |
| 224 | 14 | `CTRLS1` | `CTRLS2` | `CTRLS3` | `CTRLS4` |
| 240 | 15 | `CTRLSFNL` | `CTRLSFJT` | `TMP11` | `TMP12` |
| 256 | 16 | `PREVPTAT` | — | `ACCXB` | — |
| 272 | 17 | `1HB` | `0H` | `ASR22` | `ASR6` |
| 288 | 18 | `TMP13` | `FINTX` | `FINTY` | `FINTZ` |
| **304** | **19** | **`TMP1B`** | **`TMP2B`** | **`TMP3B`** | **`TMP4B`** |
| 320 | 20 | `STXG` | `STYG` | `STZG` | `CTRLSFJT2` |
| 336 | 21 | `PVXG` | `PVYG` | `PVZG` | — |
| 352 | 22 | `MNMFLAG` | `MNMTM` | `MNMTMTHR` | `MNMTHR` |
| 368 | 23 | `ACCQD4` | `ACCQD5` | `ACCQD6` | `ACCQD7` |
| 384 | 24 | `ACCQD0` | `ACCQD1` | `ACCQD2` | `ACCQD3` |
| 400 | 25 | `XN2` | `XN1` | `YN2` | `YN1` |
| 416 | 26 | `Y` | `B0` | `A1` | `A2` |
| 432 | 27 | `SEM1` | `SH_TH_X` | `SH_TH_Y` | `SH_TH_Z` |
| 448 | 28 | `TEMP29` | `XACCB_PRE` | `YACCB_PRE` | `ZACCB_PRE` |
| 464 | 29 | `TMP22` | `TAP_THX` | `TAP_THY` | `TAP_THZ` |
| 480 | 30 | `TMP25` | `TMP27` | `ORIENT` | `ENDIAN` |
| 496 | 31 | `BLPFNMTC` | `BLPFNMX` | `BLPFNMY` | `BLPFNMZ` |

Three pages you will use constantly:

- **Page 7 (address 112) — the constant page.** `{0.5, 0.0, 1.0, 1.5}` in Q30, i.e.
  `20000000 00000000 40000000 60000000`. Verified byte-for-byte in the image and read back on
  hardware **[HW]**. Since the ISA has **no immediate operands**, this is where every literal
  comes from. Point P0 here and word 1 becomes your zero, which is how emits and moves are built.
- **Page 19 (address 304) — the scratch page.** `TMP1B..TMP4B`. This is where `a3` points P2, and
  it is why `a3` is a safe filler.
- **Page 8 (address 128) — `TMP1A..TMP4A`**, the other scratch set, used for intermediate terms.

Pages 0, 9, 10 and 25 hold the sensor inputs and their working copies. **The hardware writes
page 0 before every pass**, int16 big-endian in the register-burst order **[HW, probe84]**:
accel X / Y / Z at `0x000` / `0x002` / `0x004`, temperature at `0x006`, gyro X / Y / Z at
`0x008` / `0x00a` / `0x00c`; `0x00e` reads a constant 12. Identified by standby: with the
accel in standby `0x000`–`0x005` freeze at the host's ACCEL_OUT values, with the gyro in
standby the gyro halves read 0. The vendor's word names (`PTAT`, `YGYR`, `XACC`, `ZACC`) label
the 32-bit words, each of which holds two of these half-words.

## 6.4 The bench view of the same thing

Early bench work catalogued memory as "bank selector × index", which is the same space seen
through a `9x` (P1 page) byte and an ALU byte's operand field. The identifications are measured
on silicon and are the ones the `dmpasm` aliases use:

| `selbank` | P1 page | field indices `20 28 30 38` |
|---|---|---|
| `0x9a` | 10 | — / gyro x / gyro y / gyro z |
| `0x9c` | 12 | quat w / quat x / quat y / quat z |
| `0x99` | 9 | — / accel x / accel y / accel z *(post-accel sites only)* |
| `0x98` | 8 | delay line |

**These are position-dependent.** The same selector reads a different address depending on the
bank in scope at that point in the program — at a post-accel site the same `9x` byte read address
272 instead of 16. What varies is the bank, not the meaning of the page. `bench/regmap.md` has
the full 16 × 16 survey with the constant/varying classification.

## 6.5 Allocating your own storage

There is no allocator and no linker. To give your program a word:

1. Pick a page inside `0x000`–`0x3FF` that the host firmware does not use. The bench uses
   **bank 2, page 4 = address 0x240 = 576** as its scratch page. Check your own host image:
   in a Family A image, keep well below 768 or you will be writing into code.
2. Write initial values from the host **after** the image load and **before** starting the DMP
   ([chapter 5](05-host-interface.md)). This is also how you supply constants the constant page
   does not have.
3. Point a pointer at it: `p2bank 2` / `p2page 4`.
4. Read it back from the host after a run to see what happened.

Remember the whole page is your unit: four words, and the destination walks them.
