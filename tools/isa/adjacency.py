#!/usr/bin/env python3
"""Adjacency-lift mining (bk3296 A16) over the pooled mantis-encoding code regions.
Questions: which bx values pair with which page family (8x/9x/ax)?  What follows/precedes
d8/d9/da?  Do d9/da bracket with d8?  What do f4 targets land on?"""
import collections, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from branch import IMAGES, code_start, br_opcode

def fam(b):
    if b < 0x80: return "low"
    return f"{b>>4:x}x"

def main():
    pooled = []
    for size, p in sorted(IMAGES.items()):
        img = p.read_bytes(); start = code_start(size)
        if br_opcode(img, start) != 0xF4: continue   # mantis encoding only
        pooled.append((size, img, start))
    print("images:", [s for s, _, _ in pooled])

    # 1. bx followed by page family
    nxt = collections.defaultdict(collections.Counter)
    for _, img, start in pooled:
        for i in range(start, len(img) - 1):
            b = img[i]
            if 0xB0 <= b <= 0xBF:
                nxt[b][fam(img[i + 1])] += 1
    print("\nbx -> family of next byte (sel = bits[3:2], bank = bits[1:0])")
    for b in range(0xB0, 0xC0):
        c = nxt[b]; tot = sum(c.values())
        if not tot: continue
        top = ", ".join(f"{k}:{v}" for k, v in c.most_common(5))
        print(f"  {b:02x} sel={(b>>2)&3} bank={b&3}  n={tot:4}  {top}")

    # 2. successor / predecessor lift for selected bytes
    base = collections.Counter(); pred = collections.defaultdict(collections.Counter); succ = collections.defaultdict(collections.Counter)
    n = 0
    for _, img, start in pooled:
        code = img[start:]
        for i, b in enumerate(code):
            base[b] += 1; n += 1
            if i + 1 < len(code): succ[b][code[i + 1]] += 1
            if i > 0: pred[b][code[i - 1]] += 1
    def lift(tbl, b, k=8):
        c = tbl[b]; tot = sum(c.values())
        rows = sorted(((v / tot) / (base[x] / n), x, v) for x, v in c.items() if v >= 3)[::-1][:k]
        return ", ".join(f"{x:02x}({v},x{l:.1f})" for l, x, v in rows)
    for b in (0xD8, 0xD9, 0xDA, 0xDB, 0xDD, 0xDE, 0xDF, 0xD0, 0xD1, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF8, 0xF9, 0xFA, 0xFE, 0xFF, 0xA3, 0xA8, 0xC0, 0xC8, 0xC9, 0xCD):
        print(f"\n  {b:02x}  n={base[b]:4}  succ: {lift(succ, b)}")
        print(f"      {'':7}       pred: {lift(pred, b)}")

    # 3. bracket structure: after d9/da, what dx comes next and how far
    print("\nd9/da: next d-family byte and distance")
    for opener in (0xD9, 0xDA):
        dist = collections.Counter(); closer = collections.Counter()
        for _, img, start in pooled:
            for i in range(start, len(img)):
                if img[i] != opener: continue
                for j in range(i + 1, min(len(img), i + 40)):
                    if 0xD8 <= img[j] <= 0xDA:
                        closer[img[j]] += 1; dist[j - i] += 1; break
        print(f"  {opener:02x}: next d8/d9/da = {dict(closer)}; distance hist = {sorted(dist.items())[:15]}")

    # 4. what byte sits at f4 targets, and right before f4
    at = collections.Counter(); before = collections.Counter(); after_pairs = collections.Counter()
    for _, img, start in pooled:
        for i in range(start, len(img) - 1):
            if img[i] == 0xF4 and img[i + 1] < 0x80:
                t = i + 2 + img[i + 1]
                if t < len(img): at[img[t]] += 1
                before[img[i - 1]] += 1
    print("\nbyte AT f4 target:", ", ".join(f"{k:02x}:{v}" for k, v in at.most_common(10)))
    print("byte BEFORE f4:   ", ", ".join(f"{k:02x}:{v}" for k, v in before.most_common(10)))

    # 5. f5/f6/f7 operand statistics
    for op in (0xF5, 0xF6, 0xF7, 0xFD):
        c = collections.Counter()
        for _, img, start in pooled:
            for i in range(start, len(img) - 1):
                if img[i] == op: c[img[i + 1]] += 1
        print(f"  {op:02x} next-byte top: ", ", ".join(f"{k:02x}:{v}" for k, v in c.most_common(12)))

if __name__ == "__main__":
    main()
