#!/usr/bin/env python3
"""dmpdis - annotating disassembler for InvenSense DMP firmware images.

Decodes what has been established so far and marks everything else UNKNOWN
rather than guessing. Confidence is explicit per instruction:

  [C] confirmed  - verified against driver behaviour or the vendor DINA table
  [P] probable   - structurally derived, consistent, not independently verified
  [?] unknown    - byte in the code region with no established meaning

Usage:
  python3 dmpdis.py <image.bin> [--symbols <dmpDefault.c>] [--start N] [--end N]
"""
import sys, re, argparse, pathlib

# --- established semantics -------------------------------------------------
# Operation classes of the low space: v = (reg << 3) | op
# The low space 0x00-0x7F holds REGISTER REFERENCES, not standalone opcodes:
# v = (reg << 3) | mode. A preceding high-space block opcode decides what is
# done with them -- `f9` (DINAF8+1) emits them to the FIFO, `fa` (DINAF8+2)
# consumes them arithmetically in the sensor-fusion routine.
OPCLASS = {
    0: ("r{reg}",     "mode 0; emitted to FIFO after f9",         "C"),
    1: ("r{reg}.m1",  "mode 1, unknown",                          "?"),
    2: ("r{reg}.m2",  "mode 2, unknown",                          "?"),
    4: ("r{reg}.acc", "accel orient/cal channel (FCFG_2)",        "C"),
    5: ("r{reg}.bias", "bias-update channel",                     "C"),
    6: ("r{reg}.gyr", "gyro orient/cal channel (FCFG_3/7)",       "C"),
}

# High space = 8 families of 16. Anchors come from the vendor DINAxx names.
HIGH_FAMILY16 = {
    0x80: ("f80",     "DINA80+{n}; bias-update block"),
    0x90: ("SRCSEL",  "DINA90+{n}; source select (95=gyro)"),
    0xa0: ("f a0",    "DINAA0+{n}; a3 = NOP, a9/af seen in fusion"),
    0xb0: ("Cm",      "Mantis-core C family (DINAC* remapped)"),
    0xc0: ("C",       "DINAC{n:X}; calibration/matrix family"),
    0xd0: ("D",       "DINAD8+{n}; d8/d9/da, most frequent family"),
    0xf0: ("BLK",     "DINAF8+{n}; block opcode, n selects operation"),
}

# High-space instructions with established meaning.
# name, operand_bytes, confidence, note
HIGH = {
    0xa3: ("NOP",       0, "C", "DINAA0+3; used as filler in disabled blocks"),
    0xf9: ("EMITBLK",   0, "C", "DINAF8+1 (6050); opens a FIFO emit block"),
    0xf1: ("EMITBLK",   0, "C", "DINAF8+1 (Mantis core)"),
    0xfa: ("EMITBLK.2", 0, "P", "DINAF8+2; alternate data width"),
    0xfb: ("EMITBLK.3", 0, "P", "DINAF8+3; alternate data width"),
    0xf4: ("OP.imm",    1, "C", "takes 1-byte immediate; solver + 90.7% successor + driver"),
    0xfd: ("OP.imm",    1, "P", "99.3% of successors < 0x80"),
    0xfe: ("SKIP",      0, "C", "disables a block (CFG_FIFO_INT off)"),
    0xff: ("DISABLE",   0, "C", "disables a block (CFG_PED_ENABLE off)"),
    0x95: ("SRCSEL.5",  0, "C", "DINA90+5; CFG_GYRO_SOURCE"),
    0x9a: ("SRCSEL.10", 0, "C", "DINA90+10; alternate gyro source"),
    0xd8: ("D8",        0, "P", "most frequent opcode; 1-byte (solver)"),
}
# solver-pinned single-byte opcodes with no semantics yet
PINNED1 = {0x89, 0x90, 0x97, 0x98, 0x9d, 0xa5, 0xb2, 0xdc}


def load_symbols(path):
    DEF = re.compile(r'#define\s+(\w+)\s+\(?\s*([0-9][0-9xXa-fA-F\s+*\-]*?)\s*\)?\s*$', re.M)
    syms = {}
    text = pathlib.Path(path).read_text(errors="ignore")
    for m in DEF.finditer(text):
        n, e = m.group(1), m.group(2).strip()
        if not re.fullmatch(r'[0-9xXa-fA-F\s+*\-]+', e):
            continue
        try:
            v = eval(e.replace('0X', '0x'), {"__builtins__": {}})
        except Exception:
            continue
        if re.match(r'(FCFG|CFG)_', n):
            syms.setdefault(v, n)
    return syms


def decode(b):
    """-> (mnemonic, operand_len, confidence, note)"""
    if b in HIGH:
        return HIGH[b]
    if b < 0x80:
        op, reg = b & 7, (b >> 3) & 0xF
        if op in OPCLASS:
            name, desc, conf = OPCLASS[op]
            return (name.format(reg=reg), 0, conf, desc)
        return (f"r{reg}.m{op}", 0, "?", "unpopulated mode")
    # High space is 8 families of 16. The vendor's `DINAxx + n` idiom reaches
    # n = 15 and crosses 8-byte boundaries (DINA90+14 = 0x9e, DINAA0+15 = 0xaf),
    # so families are 0x_0-0x_f, not 8-wide.
    fam = b & 0xF0
    idx = b & 0x0F
    if fam in HIGH_FAMILY16:
        name, note = HIGH_FAMILY16[fam]
        return (f"{name}.{idx}", 0, "P", note.format(n=idx))
    if b in PINNED1:
        return (f"i_{b:02x}", 0, "P", "solver-pinned 1-byte, semantics unknown")
    return (f"db_{b:02x}", 0, "?", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--symbols")
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    a = ap.parse_args()

    img = pathlib.Path(a.image).read_bytes()
    syms = load_symbols(a.symbols) if a.symbols else {}

    # code region: 4096 for the 14 KB ICM image, else 1024 - but Family A
    # (<=1962 B) carries code well below that, so disassemble from 0 there.
    if a.start is not None:
        start = a.start
    elif len(img) > 14000:
        start = 4096
    elif len(img) <= 1962:
        start = min(syms) if syms else 0
    else:
        start = 1024
    end = a.end if a.end is not None else len(img)

    print(f"; {a.image}  ({len(img)} bytes)   region [{start}:{end}]")
    print(f"; confidence: [C]onfirmed  [P]robable  [?]unknown\n")

    counts = {"C": 0, "P": 0, "?": 0}
    i = start
    while i < end:
        if i in syms:
            print(f"\n{syms[i]}:                      ; addr {i}")
        b = img[i]
        mnem, olen, conf, note = decode(b)
        operand = img[i+1:i+1+olen]
        raw = img[i:i+1+olen].hex(' ')
        counts[conf] = counts.get(conf, 0) + 1
        opstr = f" 0x{operand[0]:02x}" if operand else ""
        cmt = f"   ; {note}" if note else ""
        print(f"  {i:>5}  {raw:<9} [{conf}] {mnem}{opstr}{cmt}")
        i += 1 + olen

    tot = sum(counts.values())
    print(f"\n; decoded {tot} instructions: "
          f"{counts['C']} confirmed, {counts['P']} probable, {counts['?']} unknown "
          f"({100*(counts['C']+counts['P'])/tot:.1f}% attributed)")


if __name__ == "__main__":
    main()
