#!/usr/bin/env python3
"""Pointer-model test: does 'operand address = hi*256 + page*16 + 4*field' hit the vendor's
named data words far above a shuffled control?  Enumerates which bx (or cx) bit-field
feeds which pointer's high bits.

Model (from bench regmap + image bytes):
  9x  -> page of pointer P1  (B field, bits[4:3] of a low byte)     [verified]
  8x  -> page of pointer P0  (A field, bits[6:5])                   [hypothesis]
  ax  -> page of pointer P2  (destination?)                        [hypothesis]
  bx  -> mantis: bits[3:2] select a pointer, bits[1:0] its 256-B bank
  cx  -> 3050-style (1024 image): bits[2:1] select pointer, bit 0 its bank
"""
import random, itertools, collections, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from symbols import symbols, data_labels, dmpmap, ROOT
from branch import load, code_start, br_opcode

def walk(img, start, assign, hi_family, data_size):
    """assign: tuple mapping bx pointer-select value (0..3) -> pointer index 0/1/2 or None."""
    page = [0, 0, 0]; hi = [0, 0, 0]
    A = []; B = []; D = []
    op = br_opcode(img, start)
    i = start
    while i < len(img):
        b = img[i]
        if b == op:
            i += 2; continue
        fam = b >> 4
        if fam == 8: page[0] = b & 0xf
        elif fam == 9: page[1] = b & 0xf
        elif fam == 0xA: page[2] = b & 0xf
        elif fam == hi_family:
            if hi_family == 0xB:
                sel, bank = (b >> 2) & 3, b & 3
            else:  # cx, 3050 style
                sel, bank = (b >> 1) & 3, b & 1
            p = assign[sel]
            if p is not None: hi[p] = bank
        elif b < 0x80:
            a_f, b_f = (b >> 5) & 3, (b >> 3) & 3
            A.append(hi[0] * 256 + page[0] * 16 + 4 * a_f)
            B.append(hi[1] * 256 + page[1] * 16 + 4 * b_f)
            D.append(hi[2] * 256 + page[2] * 16 + 4 * b_f)
        i += 1
    return A, B, D

def hitrate(addrs, labwords, data_size):
    ok = [a for a in addrs if a < data_size]
    if not ok: return 0.0, 0
    return sum(1 for a in ok if a // 4 in labwords) / len(ok), len(ok)

def main():
    random.seed(2)
    syms = symbols()
    dm = dmpmap()
    cases = [(3062, syms[3062], 1024, 0xB), (2639, syms[2639], 1024, 0xB),
             (1024, {**dm}, 512, 0xC), (1923, {**dm}, 512, 0xB)]
    for size, sym, data_size, hifam in cases:
        img = load(size); start = code_start(size)
        labs = data_labels(sym) if size in (3062, 2639) else sym
        labwords = {v // 4 for v in labs.values() if v < data_size}
        base = len(labwords) / (data_size // 4)
        print(f"\n=== {size} B  data={data_size}  labelled words={len(labwords)}  chance={base:.3f}")
        results = []
        assigns = [(0, 1, 2, None), (0, 2, 1, None), (1, 0, 2, None), (1, 2, 0, None),
                   (2, 0, 1, None), (2, 1, 0, None), (None, None, None, None)]
        for asg in assigns:
            A, B, D = walk(img, start, asg, hifam, data_size)
            ra, na = hitrate(A, labwords, data_size)
            rb, nb = hitrate(B, labwords, data_size)
            rd, nd = hitrate(D, labwords, data_size)
            results.append((asg, ra, rb, rd, na, nb, nd))
        # control: shuffle code bytes (keeps byte distribution, destroys structure)
        code = bytearray(img[start:]); random.shuffle(code)
        sh = bytes(img[:start]) + bytes(code)
        A, B, D = walk(sh, start, (0, 1, 2, None), hifam, data_size)
        ca, _ = hitrate(A, labwords, data_size); cb, _ = hitrate(B, labwords, data_size); cd, _ = hitrate(D, labwords, data_size)
        print(f"  {'bx sel->ptr':16} {'A(8x)':>8} {'B(9x)':>8} {'D(ax)':>8}   n(A/B/D in range)")
        for asg, ra, rb, rd, na, nb, nd in results:
            print(f"  {str(asg):16} {ra:8.3f} {rb:8.3f} {rd:8.3f}   {na}/{nb}/{nd}")
        print(f"  {'shuffled ctrl':16} {ca:8.3f} {cb:8.3f} {cd:8.3f}")

if __name__ == "__main__":
    main()
