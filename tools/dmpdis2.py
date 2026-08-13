#!/usr/bin/env python3
"""dmpdis2 - disassembler for InvenSense DMP firmware.

Instruction model (corrected by bench round 10): a **low byte is an EMIT
instruction in its own right** - it emits register (v>>3) from the bank in
scope, 4 bytes, to the FIFO. It is NOT an operand of a preceding block opcode.
Measured directly: `28 a3 a3 a3 a3` emits one register and `f1 28 30 38 a3`
emits three - identical to `28 30 38 a3 a3`, so the `f8+n` byte contributes
nothing to emission and is a separate, still-unknown instruction.

Bank state is tracked across instructions so register references can be named.

Lineage matters too. The vendor renumbered opcodes between core revisions
(confirmed in dmpKey.h and by differential analysis), so the same instruction
has different encodings:

    role            6050 lineage    Mantis lineage
    block base      0xf8            0xf0
    emit block      0xf9            0xf1
    imm-taker       0xfc            0xf4
    C family        0xc0-0xc5       0xb0-0xb9

Confidence is explicit and never inflated:
    [C] verified on hardware or against driver behaviour
    [P] structurally placed in a named vendor family; semantics unknown
    [?] unattributed

Usage:
    python3 dmpdis2.py <image.bin> [--start N] [--end N] [--summary]
"""
import argparse, collections, pathlib, sys

# ---------------------------------------------------------------- lineage ---
LINEAGES = {
    "6050":   dict(block=0xF8, emit=0xF9, imm=0xFC, cfam=(0xC0, 0xC5)),
    "mantis": dict(block=0xF0, emit=0xF1, imm=0xF4, cfam=(0xB0, 0xB9)),
}


def detect_lineage(img, start):
    code = img[start:]
    m = sum(code.count(b) for b in range(0xF0, 0xF4)) + \
        sum(code.count(b) for b in range(0xB0, 0xBA))
    s = sum(code.count(b) for b in range(0xF8, 0xFC)) + \
        sum(code.count(b) for b in range(0xC0, 0xC6))
    return "mantis" if m >= s else "6050"


# ------------------------------------------------------------ register map ---
# Verified on MPU-6050 silicon. Contents are program-position dependent: the
# same bank/index reads differently depending on where it is read from, so
# these names are annotated as hints, not guarantees.
REGMAP = {
    0x9A: {0x28: "gyro_x", 0x30: "gyro_y", 0x38: "gyro_z"},
    0x9C: {0x20: "quat_w", 0x28: "quat_x", 0x30: "quat_y", 0x38: "quat_z"},
    0x99: {0x28: "accel_x", 0x30: "accel_y", 0x38: "accel_z"},
    0x98: {0x28: "delay_t", 0x38: "delay_t1"},
}

HIGH_FAMILY = {0x80: "f80", 0x90: "SELBANK", 0xA0: "fa0", 0xB0: "Cm",
               0xC0: "C", 0xD0: "D", 0xE0: "fe0", 0xF0: "F"}

NAMED = {0xA3: ("NOP", "C", "DINAA0+3; filler / disables code in place"),
         0xFE: ("SKIP", "C", "block disable (CFG_FIFO_INT off)"),
         0xFF: ("DISABLE", "C", "block disable (CFG_PED_ENABLE off)"),
         0x95: ("SRCSEL.5", "C", "DINA90+5; CFG_GYRO_SOURCE")}


class Decoder:
    def __init__(self, img, lineage):
        self.img = img
        self.L = LINEAGES[lineage]
        self.lineage = lineage
        self.bank = None
        self.counts = collections.Counter()

    def regname(self, v):
        reg = v >> 3
        mode = v & 7
        base = f"r{reg}"
        if self.bank in REGMAP and (v & ~7) in REGMAP[self.bank]:
            base = REGMAP[self.bank][v & ~7]
        elif self.bank in REGMAP:
            base = f"r{reg}"
        if mode & 2:
            return f"{base}.z", "C", "bit1 set -> reads zero, inert"
        return base, "C", ""

    def step(self, i):
        """-> (length, mnemonic, confidence, comment, operand_run)"""
        b = self.img[i]
        L = self.L

        if b in NAMED:
            m, c, note = NAMED[b]
            return 1, m, c, note, []

        # f-family: 1-byte, except the immediate-taker
        if L["block"] <= b <= L["block"] + 7:
            n = b - L["block"]
            if b == L["imm"]:
                imm = self.img[i + 1] if i + 1 < len(self.img) else 0
                return 2, f"f{n}.imm 0x{imm:02x}", "?", \
                       "2-byte; immediate alters output composition; NOT a branch", []
            return 1, f"F.{n}", "P", \
                   f"DINAF8+{n}; not required for emission (round 10)", []

        # bank selector
        if 0x90 <= b <= 0x9F:
            self.bank = b
            known = " (mapped)" if b in REGMAP else ""
            return 1, f"SELBANK 0x{b:02x}", "C", f"DINA90+{b-0x90}{known}", []

        if b >= 0x80:
            fam = b & 0xF0
            return 1, f"{HIGH_FAMILY.get(fam, 'x')}.{b & 0x0F}", "P", \
                   f"family 0x{fam:02x}", []

        # low byte = EMIT instruction (verified: emits 4 B per byte)
        nm, c, note = self.regname(b)
        return 1, f"EMIT {nm}", "C", note or "4 B -> FIFO", []


def q30(w):
    v = int.from_bytes(w, "big", signed=True)
    return v / 2**30


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--data", action="store_true", help="also dump the data region as Q30")
    a = ap.parse_args()

    img = pathlib.Path(a.image).read_bytes()
    start = a.start if a.start is not None else (4096 if len(img) > 14000
                                                 else 1024 if len(img) > 1024 else 0)
    end = a.end if a.end is not None else len(img)
    if start >= len(img):
        sys.exit(f"start {start} beyond image ({len(img)} B)")

    lin = detect_lineage(img, start)
    d = Decoder(img, lin)

    print(f"; {a.image}  {len(img)} B   lineage={lin}   "
          f"block base 0x{LINEAGES[lin]['block']:02x}, emit 0x{LINEAGES[lin]['emit']:02x}")
    print(f"; code region [{start}:{end}]   [C]onfirmed [P]robable [?]unknown")

    if a.data and start:
        print(f"\n; ---- data region [0:{start}] as Q30 ----")
        for off in range(0, min(start, len(img)) - 3, 4):
            w = img[off:off + 4]
            if any(w):
                print(f"  {off:>5}  {w.hex(' ')}  {q30(w):+.6f}")

    print()
    i = start
    while i < end:
        n, mnem, conf, note, ops = d.step(i)
        raw = img[i:i + n].hex(' ')
        d.counts[conf] += 1
        cmt = f"   ; {note}" if note else ""
        print(f"  {i:>5}  {raw:<20} [{conf}] {mnem}{cmt}")
        i += n

    tot = sum(d.counts.values())
    print(f"\n; {tot} instructions: {d.counts['C']} confirmed, "
          f"{d.counts['P']} probable, {d.counts['?']} unknown"
          f"   ({100*d.counts['C']/max(tot,1):.1f}% verified)")


if __name__ == "__main__":
    main()
